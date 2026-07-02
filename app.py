"""
Smart Salon & Parlour - Full Stack Flask + Firebase Application
------------------------------------------------------------------
Database : Firebase Firestore
Auth     : Firebase Authentication (Admin SDK for register, REST API for login
           and password reset)
Images   : Local folder static/uploads (Firebase Storage needs the paid Blaze
           plan, so this stays on the free Spark plan)
Email    : EmailJS (browser-side) notifies staff when a customer books them
PDF      : fpdf2 generates a downloadable invoice

SETUP REQUIRED BEFORE RUNNING (fill these in below):
  1. FIREBASE_SERVICE_ACCOUNT_KEY -> path to your serviceAccountKey.json
  2. FIREBASE_WEB_API_KEY -> Firebase Console -> Project settings -> General
     (or Google Cloud Console -> APIs & Services -> Credentials -> Browser key)
  3. EmailJS keys go in static/js/config.js

Run with:  python app.py
Then open: http://127.0.0.1:5000
"""

import os
import json
import re
import requests
from datetime import datetime, date

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_file, abort
)
from werkzeug.utils import secure_filename
from fpdf import FPDF

import firebase_admin
from firebase_admin import credentials, firestore, auth

# ----------------------------------------------------------------------
# APP CONFIG
# ----------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
INVOICE_FOLDER = os.path.join(BASE_DIR, "static", "invoices")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "smart_salon_secret_key_change_this")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INVOICE_FOLDER, exist_ok=True)

# ----------------------------------------------------------------------
# FIREBASE CONFIG
# ----------------------------------------------------------------------
# Local development: put serviceAccountKey.json in this folder (used automatically).
# Deployment (Render/Railway/etc.): set these as environment variables instead —
#   FIREBASE_SERVICE_ACCOUNT_JSON = the *entire contents* of serviceAccountKey.json
#   FIREBASE_WEB_API_KEY          = your Firebase Web API Key
FIREBASE_SERVICE_ACCOUNT_KEY_PATH = os.path.join(BASE_DIR, "serviceAccountKey.json")
FIREBASE_WEB_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "PASTE_YOUR_FIREBASE_WEB_API_KEY_HERE")

service_account_json_env = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
if service_account_json_env:
    cred = credentials.Certificate(json.loads(service_account_json_env))
else:
    cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_KEY_PATH)

firebase_admin.initialize_app(cred)
db = firestore.client()

IDENTITY_TOOLKIT_BASE = "https://identitytoolkit.googleapis.com/v1/accounts"
SIGNIN_URL = f"{IDENTITY_TOOLKIT_BASE}:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
RESET_PASSWORD_URL = f"{IDENTITY_TOOLKIT_BASE}:sendOobCode?key={FIREBASE_WEB_API_KEY}"

# ----------------------------------------------------------------------
# DEFAULT USERS
# ----------------------------------------------------------------------
ADMIN_EMAIL = "navamuthu2007@gmail.com"
STAFF_ACCOUNTS = [
    ("staff1", "staff1@gmail.com"),
    ("staff2", "staff2@gmail.com"),
    ("staff3", "staff3@gmail.com"),
    ("staff4", "staff4@gmail.com"),
]
DEFAULT_PASSWORD = "12345678"

# ----------------------------------------------------------------------
# SERVICES CATALOG  (name, display price range, exact price used for totals)
# ----------------------------------------------------------------------
SERVICES = {
    "Hair Care": [
        ("Hair cutting", "100-200", 150),
        ("Styling", "200-500", 350),
        ("Coloring", "300-500", 400),
    ],
    "Skin Care": [
        ("Facials", "300-500", 400),
        ("Clean-up", "200-300", 250),
        ("Bleaching", "300-500", 400),
    ],
    "Makeup": [
        ("Bridal", "3000-6000", 4500),
        ("Party", "1000-2000", 1500),
    ],
    "Hand & Foot": [
        ("Manicure", "300-500", 400),
        ("Pedicure", "400-600", 500),
    ],
    "Hair Removal": [
        ("Threading", "400-600", 500),
        ("Waxing", "500-700", 600),
    ],
    "Spa": [
        ("Head massage", "300-500", 400),
        ("Basic spa", "800-1500", 1150),
    ],
}

STAFF_NAMES = ["staff1", "staff2", "staff3", "staff4"]


# ----------------------------------------------------------------------
# FIREBASE / FIRESTORE HELPERS
# ----------------------------------------------------------------------
def staff_email_by_name(name):
    for n, e in STAFF_ACCOUNTS:
        if n == name:
            return e
    return None


def seed_default_users():
    defaults = [("Admin", ADMIN_EMAIL, "admin")] + [
        (name, email, "staff") for name, email in STAFF_ACCOUNTS
    ]
    for username, email, role in defaults:
        try:
            user = auth.get_user_by_email(email)
        except auth.UserNotFoundError:
            user = auth.create_user(email=email, password=DEFAULT_PASSWORD, display_name=username)

        profile_ref = db.collection("users").document(user.uid)
        if not profile_ref.get().exists:
            profile_ref.set({"username": username, "email": email, "role": role})


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image_locally(file, uid):
    filename = secure_filename(f"{uid}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename


def is_strong_password(password):
    """At least 6 characters, 1 uppercase, 1 lowercase, 1 number, 1 special symbol."""
    if len(password) < 6:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"[0-9]", password):
        return False
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        return False
    return True


def doc_to_dict(doc):
    data = doc.to_dict()
    data["id"] = doc.id
    return data


def next_booking_code():
    """Atomically increments a Firestore counter and returns a code like SSP-0001."""
    counter_ref = db.collection("counters").document("bookings")

    @firestore.transactional
    def _increment(transaction):
        snapshot = counter_ref.get(transaction=transaction)
        current = snapshot.get("count") if snapshot.exists else 0
        new_count = (current or 0) + 1
        transaction.set(counter_ref, {"count": new_count})
        return new_count

    transaction = db.transaction()
    count = _increment(transaction)
    return f"SSP-{count:04d}"


# ----------------------------------------------------------------------
# AUTH HELPERS
# ----------------------------------------------------------------------
def current_user():
    if "uid" not in session:
        return None
    doc = db.collection("users").document(session["uid"]).get()
    if not doc.exists:
        return None
    return doc_to_dict(doc)


def login_required(role=None):
    def decorator(f):
        from functools import wraps

        @wraps(f)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please login to continue.", "warning")
                return redirect(url_for("login"))
            if role and user["role"] != role:
                flash("You are not authorized to view that page.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)

        return wrapped

    return decorator


# ----------------------------------------------------------------------
# ROUTES - PUBLIC
# ----------------------------------------------------------------------
@app.route("/")
def index():
    reviews = [doc_to_dict(d) for d in db.collection("reviews").stream()]
    total_reviews = len(reviews)
    avg_rating = round(sum(r["rating"] for r in reviews) / total_reviews, 1) if total_reviews else 0
    recent_reviews = sorted(reviews, key=lambda r: r.get("created_at", ""), reverse=True)[:5]

    return render_template(
        "index.html",
        avg_rating=avg_rating,
        total_reviews=total_reviews,
        recent_reviews=recent_reviews,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        if not is_strong_password(password):
            flash(
                "Password must be at least 6 characters and include an uppercase letter, "
                "a lowercase letter, a number, and a special symbol.",
                "danger",
            )
            return redirect(url_for("register"))

        try:
            auth.get_user_by_email(email)
            flash("An account with this email already exists. Please login.", "danger")
            return redirect(url_for("login"))
        except auth.UserNotFoundError:
            pass

        if email == ADMIN_EMAIL:
            role = "admin"
        elif email in [e for _, e in STAFF_ACCOUNTS]:
            role = "staff"
        else:
            role = "customer"

        try:
            user = auth.create_user(email=email, password=password, display_name=username)
        except Exception as e:
            flash(f"Registration failed: {e}", "danger")
            return redirect(url_for("register"))

        db.collection("users").document(user.uid).set(
            {"username": username, "email": email, "role": role}
        )

        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        try:
            resp = requests.post(
                SIGNIN_URL,
                json={"email": email, "password": password, "returnSecureToken": True},
                timeout=10,
            )
            data = resp.json()
            if resp.status_code != 200:
                flash("Invalid email or password.", "danger")
                return redirect(url_for("login"))
            uid = data["localId"]
        except requests.exceptions.RequestException:
            flash("Could not reach Firebase. Check your internet connection.", "danger")
            return redirect(url_for("login"))

        profile_doc = db.collection("users").document(uid).get()
        if not profile_doc.exists:
            flash("No profile found for this account.", "danger")
            return redirect(url_for("login"))

        profile = profile_doc.to_dict()
        session["uid"] = uid
        session["username"] = profile["username"]
        session["role"] = profile["role"]
        flash(f"Welcome back, {profile['username']}!", "success")

        if profile["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        elif profile["role"] == "staff":
            return redirect(url_for("staff_dashboard"))
        else:
            return redirect(url_for("customer_dashboard"))

    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        try:
            auth.get_user_by_email(email)
            # Ask Firebase itself to email a reset link — no SMTP setup needed.
            requests.post(
                RESET_PASSWORD_URL,
                json={"requestType": "PASSWORD_RESET", "email": email},
                timeout=10,
            )
        except auth.UserNotFoundError:
            pass  # Don't reveal whether the email exists
        except requests.exceptions.RequestException:
            pass

        flash("If that email is registered, a password reset link has been sent.", "info")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ----------------------------------------------------------------------
# ROUTES - CUSTOMER
# ----------------------------------------------------------------------
@app.route("/customer/dashboard")
@login_required(role="customer")
def customer_dashboard():
    last_booking = session.pop("last_booking", None)
    return render_template("customer_dashboard.html", username=session["username"], last_booking=last_booking)


@app.route("/customer/booking", methods=["GET", "POST"])
@login_required(role="customer")
def booking():
    if request.method == "POST":
        services_selected = request.form.getlist("services")
        staff_name = request.form.get("staff_name")
        date_ = request.form.get("date")
        time_ = request.form.get("time")
        seat = request.form.get("seat")

        if not services_selected or not staff_name or not date_ or not time_ or not seat:
            flash("Please fill all required fields and select at least one service.", "danger")
            return redirect(url_for("booking"))

        clash = (
            db.collection("bookings")
            .where("date", "==", date_)
            .where("time", "==", time_)
            .where("seat", "==", seat)
            .limit(1)
            .get()
        )
        if len(clash) > 0:
            flash("This seat is already booked for the selected date & time. Please choose another slot.", "danger")
            return redirect(url_for("booking"))

        # Build service breakdown + total price from the catalog (never trust
        # a price sent from the browser).
        price_lookup = {}
        for items in SERVICES.values():
            for name, _range, price in items:
                price_lookup[name] = price

        service_items = []
        total_price = 0
        for raw in services_selected:
            name = raw.split(" (")[0]  # value format: "Hair cutting (₹100-200)"
            price = price_lookup.get(name, 0)
            service_items.append({"name": name, "price": price})
            total_price += price

        image_filename = None
        file = request.files.get("image")
        if file and file.filename and allowed_file(file.filename):
            image_filename = save_image_locally(file, session["uid"])

        booking_code = next_booking_code()
        staff_email = staff_email_by_name(staff_name)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        services_str = ", ".join(s["name"] for s in service_items)

        db.collection("bookings").add(
            {
                "booking_code": booking_code,
                "user_id": session["uid"],
                "customer_name": session["username"],
                "services": services_str,
                "service_items": service_items,
                "total_price": total_price,
                "staff_name": staff_name,
                "staff_email": staff_email,
                "date": date_,
                "time": time_,
                "seat": seat,
                "image": image_filename,
                "status": "Pending",
                "created_at": created_at,
            }
        )

        session["last_booking"] = {
            "staff_name": staff_name,
            "staff_email": staff_email,
            "customer_name": session["username"],
            "services": services_str,
            "date": date_,
            "time": time_,
            "seat": seat,
            "booking_code": booking_code,
        }

        flash(f"Booking confirmed! Your booking ID is {booking_code}.", "success")
        return redirect(url_for("invoice", booking_code=booking_code))

    return render_template("booking.html", services=SERVICES, staff_names=STAFF_NAMES)


@app.route("/customer/invoice/<booking_code>")
@login_required()
def invoice(booking_code):
    docs = db.collection("bookings").where("booking_code", "==", booking_code).limit(1).get()
    if not docs:
        abort(404)
    b = doc_to_dict(docs[0])

    user = current_user()
    if user["role"] == "customer" and b["user_id"] != session["uid"]:
        flash("You are not authorized to view that invoice.", "danger")
        return redirect(url_for("customer_dashboard"))

    return render_template("invoice.html", b=b)


@app.route("/customer/invoice/<booking_code>/pdf")
@login_required()
def invoice_pdf(booking_code):
    docs = db.collection("bookings").where("booking_code", "==", booking_code).limit(1).get()
    if not docs:
        abort(404)
    b = doc_to_dict(docs[0])

    user = current_user()
    if user["role"] == "customer" and b["user_id"] != session["uid"]:
        abort(403)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Smart Salon & Parlour", ln=True, align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "Invoice", ln=True, align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Booking ID: {b['booking_code']}", ln=True)
    pdf.cell(0, 8, f"Customer: {b['customer_name']}", ln=True)
    pdf.cell(0, 8, f"Staff: {b['staff_name']}", ln=True)
    pdf.cell(0, 8, f"Date: {b['date']}    Time: {b['time']}    Seat: {b['seat']}", ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(120, 8, "Service", border=1)
    pdf.cell(60, 8, "Price (Rs.)", border=1, ln=True)

    pdf.set_font("Helvetica", "", 11)
    for item in b.get("service_items", []):
        pdf.cell(120, 8, item["name"], border=1)
        pdf.cell(60, 8, str(item["price"]), border=1, ln=True)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(120, 10, "Total", border=1)
    pdf.cell(60, 10, str(b.get("total_price", 0)), border=1, ln=True)

    pdf_path = os.path.join(INVOICE_FOLDER, f"{b['booking_code']}.pdf")
    pdf.output(pdf_path)

    return send_file(pdf_path, as_attachment=True, download_name=f"{b['booking_code']}_invoice.pdf")


@app.route("/customer/review", methods=["GET", "POST"])
@login_required(role="customer")
def review():
    if request.method == "POST":
        staff_name = request.form.get("staff_name")
        rating = request.form.get("rating")
        feedback = request.form.get("feedback", "").strip()

        if not staff_name or not rating:
            flash("Please select a staff member and a rating.", "danger")
            return redirect(url_for("review"))

        db.collection("reviews").add(
            {
                "user_id": session["uid"],
                "customer_name": session["username"],
                "staff_name": staff_name,
                "rating": int(rating),
                "feedback": feedback,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        )

        flash("Thank you for your feedback!", "success")
        return redirect(url_for("customer_dashboard"))

    return render_template("review.html", staff_names=STAFF_NAMES)


@app.route("/customer/profile", methods=["GET", "POST"])
@login_required(role="customer")
def profile():
    uid = session["uid"]

    if request.method == "POST":
        new_username = request.form.get("username", "").strip()
        if new_username:
            db.collection("users").document(uid).update({"username": new_username})
            session["username"] = new_username
            flash("Profile updated.", "success")
        return redirect(url_for("profile"))

    user = current_user()
    docs = db.collection("bookings").where("user_id", "==", uid).stream()
    bookings = [doc_to_dict(d) for d in docs]
    bookings.sort(key=lambda b: b.get("created_at", ""), reverse=True)

    return render_template("profile.html", user=user, bookings=bookings)


# ----------------------------------------------------------------------
# ROUTES - STAFF
# ----------------------------------------------------------------------
@app.route("/staff/dashboard")
@login_required(role="staff")
def staff_dashboard():
    docs = db.collection("bookings").where("staff_name", "==", session["username"]).stream()
    bookings = [doc_to_dict(d) for d in docs]
    bookings.sort(key=lambda b: b.get("created_at", ""), reverse=True)

    return render_template("staff_dashboard.html", bookings=bookings, username=session["username"])


@app.route("/staff/update_status/<booking_id>", methods=["POST"])
@login_required(role="staff")
def update_status(booking_id):
    new_status = request.form.get("status")
    db.collection("bookings").document(booking_id).update({"status": new_status})
    flash("Booking status updated.", "success")
    return redirect(url_for("staff_dashboard"))


# ----------------------------------------------------------------------
# ROUTES - ADMIN
# ----------------------------------------------------------------------
@app.route("/admin/dashboard")
@login_required(role="admin")
def admin_dashboard():
    all_bookings = [doc_to_dict(d) for d in db.collection("bookings").stream()]
    total_bookings = len(all_bookings)

    total_customers = len(list(db.collection("users").where("role", "==", "customer").stream()))

    all_bookings.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    recent_bookings = all_bookings[:10]

    # ---- Analytics: bookings per day (last 7 days) ----
    per_day_counts = {}
    for b in all_bookings:
        d = b.get("date", "")
        if d:
            per_day_counts[d] = per_day_counts.get(d, 0) + 1
    chart_labels = sorted(per_day_counts.keys())[-7:]
    chart_values = [per_day_counts[d] for d in chart_labels]

    # ---- Analytics: revenue this month ----
    this_month = date.today().strftime("%Y-%m")
    revenue_this_month = sum(
        b.get("total_price", 0) for b in all_bookings if b.get("date", "").startswith(this_month)
    )

    return render_template(
        "admin_dashboard.html",
        total_bookings=total_bookings,
        total_customers=total_customers,
        recent_bookings=recent_bookings,
        chart_labels=chart_labels,
        chart_values=chart_values,
        revenue_this_month=revenue_this_month,
    )


@app.route("/admin/reviews")
@login_required(role="admin")
def reviews_page():
    reviews = [doc_to_dict(d) for d in db.collection("reviews").stream()]
    reviews.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return render_template("reviews.html", reviews=reviews)


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
if __name__ == "__main__":
    seed_default_users()
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)