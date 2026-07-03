"""
Smart Salon & Parlour - Full Stack Flask + SQLite Application
------------------------------------------------------------------
Database : SQLite (salon.db, created automatically)
Auth     : Custom (Werkzeug password hashing) — no external service needed
Images   : Local folder static/uploads
Email    : EmailJS (browser-side) notifies staff when a customer books them
PDF      : fpdf2 generates a downloadable invoice

Works fully offline-friendly on free hosts like PythonAnywhere (no external
API calls required for login/database — only the browser needs internet for
the EmailJS notification).

Run with:  python app.py
Then open: http://127.0.0.1:5000
"""

import os
import re
import sqlite3
from datetime import datetime, date

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_file, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from fpdf import FPDF

# ----------------------------------------------------------------------
# APP CONFIG
# ----------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "salon.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
INVOICE_FOLDER = os.path.join(BASE_DIR, "static", "invoices")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "smart_salon_secret_key_change_this")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INVOICE_FOLDER, exist_ok=True)

# ----------------------------------------------------------------------
# DEFAULT USERS
# ----------------------------------------------------------------------
ADMIN_EMAIL = "navamuthu2007@gmail.com"
STAFF_ACCOUNTS = [
    ("staff1", "navamuthu2507@gmail.com"),
    ("staff2", "navamuthu2225@gmail.com"),
    ("staff3", "staff3@gmail.com"),
    ("staff4", "staff4@gmail.com"),
]
DEFAULT_PASSWORD = "Salon@123"

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
# DATABASE HELPERS
# ----------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_code TEXT UNIQUE,
            user_id INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            services TEXT NOT NULL,
            total_price INTEGER DEFAULT 0,
            staff_name TEXT NOT NULL,
            staff_email TEXT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            seat INTEGER NOT NULL,
            image TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS booking_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            service_name TEXT NOT NULL,
            price INTEGER NOT NULL,
            FOREIGN KEY (booking_id) REFERENCES bookings(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            staff_name TEXT NOT NULL,
            rating INTEGER NOT NULL,
            feedback TEXT,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()

    # Seed admin
    cur.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
            ("Admin", ADMIN_EMAIL, generate_password_hash(DEFAULT_PASSWORD), "admin"),
        )

    # Seed staff
    for name, email in STAFF_ACCOUNTS:
        cur.execute("SELECT id FROM users WHERE email = ?", (email,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
                (name, email, generate_password_hash(DEFAULT_PASSWORD), "staff"),
            )

    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def staff_email_by_name(name):
    for n, e in STAFF_ACCOUNTS:
        if n == name:
            return e
    return None


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


# ----------------------------------------------------------------------
# AUTH HELPERS
# ----------------------------------------------------------------------
def current_user():
    if "user_id" not in session:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return user


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
    conn = get_db()
    reviews = conn.execute(
        "SELECT AVG(rating) as avg_rating, COUNT(*) as total FROM reviews"
    ).fetchone()
    recent_reviews = conn.execute(
        "SELECT * FROM reviews ORDER BY id DESC LIMIT 5"
    ).fetchall()
    conn.close()

    avg_rating = round(reviews["avg_rating"], 1) if reviews["avg_rating"] else 0
    total_reviews = reviews["total"] or 0

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

        conn = get_db()
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.close()
            flash("An account with this email already exists. Please login.", "danger")
            return redirect(url_for("login"))

        if email == ADMIN_EMAIL:
            role = "admin"
        elif email in [e for _, e in STAFF_ACCOUNTS]:
            role = "staff"
        else:
            role = "customer"

        conn.execute(
            "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
            (username, email, generate_password_hash(password), role),
        )
        conn.commit()
        conn.close()

        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['username']}!", "success")

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            elif user["role"] == "staff":
                return redirect(url_for("staff_dashboard"))
            else:
                return redirect(url_for("customer_dashboard"))
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        new_password = request.form.get("new_password", "")

        if not is_strong_password(new_password):
            flash(
                "New password must be at least 6 characters and include an uppercase letter, "
                "a lowercase letter, a number, and a special symbol.",
                "danger",
            )
            return redirect(url_for("forgot_password"))

        conn = get_db()
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            conn.execute(
                "UPDATE users SET password = ? WHERE id = ?",
                (generate_password_hash(new_password), user["id"]),
            )
            conn.commit()
        conn.close()

        # Don't reveal whether the email existed — same message either way
        flash("If that email is registered, your password has been updated. Please login.", "info")
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

        conn = get_db()

        clash = conn.execute(
            "SELECT id FROM bookings WHERE date = ? AND time = ? AND seat = ?",
            (date_, time_, seat),
        ).fetchone()
        if clash:
            conn.close()
            flash("This seat is already booked for the selected date & time. Please choose another slot.", "danger")
            return redirect(url_for("booking"))

        price_lookup = {}
        for items in SERVICES.values():
            for name, _range, price in items:
                price_lookup[name] = price

        service_items = []
        total_price = 0
        for raw in services_selected:
            name = raw.split(" (")[0]
            price = price_lookup.get(name, 0)
            service_items.append((name, price))
            total_price += price

        image_filename = None
        file = request.files.get("image")
        if file and file.filename and allowed_file(file.filename):
            image_filename = secure_filename(
                f"{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
            )
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], image_filename))

        services_str = ", ".join(name for name, _price in service_items)
        staff_email = staff_email_by_name(staff_name)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        cur = conn.execute(
            """INSERT INTO bookings
               (user_id, customer_name, services, total_price, staff_name, staff_email,
                date, time, seat, image, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session["user_id"], session["username"], services_str, total_price,
                staff_name, staff_email, date_, time_, seat, image_filename, "Pending", created_at,
            ),
        )
        booking_id = cur.lastrowid
        booking_code = f"SSP-{booking_id:04d}"
        conn.execute("UPDATE bookings SET booking_code = ? WHERE id = ?", (booking_code, booking_id))

        for name, price in service_items:
            conn.execute(
                "INSERT INTO booking_items (booking_id, service_name, price) VALUES (?, ?, ?)",
                (booking_id, name, price),
            )

        conn.commit()
        conn.close()

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


def _get_booking_with_items(booking_code):
    conn = get_db()
    b = conn.execute("SELECT * FROM bookings WHERE booking_code = ?", (booking_code,)).fetchone()
    if not b:
        conn.close()
        return None
    items = conn.execute(
        "SELECT service_name as name, price FROM booking_items WHERE booking_id = ?", (b["id"],)
    ).fetchall()
    conn.close()
    b = dict(b)
    b["service_items"] = [dict(i) for i in items]
    return b


@app.route("/customer/invoice/<booking_code>")
@login_required()
def invoice(booking_code):
    b = _get_booking_with_items(booking_code)
    if not b:
        abort(404)

    user = current_user()
    if user["role"] == "customer" and b["user_id"] != session["user_id"]:
        flash("You are not authorized to view that invoice.", "danger")
        return redirect(url_for("customer_dashboard"))

    return render_template("invoice.html", b=b)


@app.route("/customer/invoice/<booking_code>/pdf")
@login_required()
def invoice_pdf(booking_code):
    b = _get_booking_with_items(booking_code)
    if not b:
        abort(404)

    user = current_user()
    if user["role"] == "customer" and b["user_id"] != session["user_id"]:
        abort(403)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Smart Salon & Parlour", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "Invoice", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Booking ID: {b['booking_code']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Customer: {b['customer_name']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Staff: {b['staff_name']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Date: {b['date']}    Time: {b['time']}    Seat: {b['seat']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(120, 8, "Service", border=1)
    pdf.cell(60, 8, "Price (Rs.)", border=1, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 11)
    for item in b["service_items"]:
        pdf.cell(120, 8, item["name"], border=1)
        pdf.cell(60, 8, str(item["price"]), border=1, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(120, 10, "Total", border=1)
    pdf.cell(60, 10, str(b["total_price"]), border=1, new_x="LMARGIN", new_y="NEXT")

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

        conn = get_db()
        conn.execute(
            """INSERT INTO reviews (user_id, customer_name, staff_name, rating, feedback, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session["user_id"], session["username"], staff_name, int(rating), feedback,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ),
        )
        conn.commit()
        conn.close()

        flash("Thank you for your feedback!", "success")
        return redirect(url_for("customer_dashboard"))

    return render_template("review.html", staff_names=STAFF_NAMES)


@app.route("/customer/profile", methods=["GET", "POST"])
@login_required(role="customer")
def profile():
    uid = session["user_id"]
    conn = get_db()

    if request.method == "POST":
        new_username = request.form.get("username", "").strip()
        if new_username:
            conn.execute("UPDATE users SET username = ? WHERE id = ?", (new_username, uid))
            conn.commit()
            session["username"] = new_username
            flash("Profile updated.", "success")
        conn.close()
        return redirect(url_for("profile"))

    user = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    bookings = conn.execute(
        "SELECT * FROM bookings WHERE user_id = ? ORDER BY id DESC", (uid,)
    ).fetchall()
    conn.close()

    return render_template("profile.html", user=user, bookings=bookings)


# ----------------------------------------------------------------------
# ROUTES - STAFF
# ----------------------------------------------------------------------
@app.route("/staff/dashboard")
@login_required(role="staff")
def staff_dashboard():
    conn = get_db()
    bookings = conn.execute(
        "SELECT * FROM bookings WHERE staff_name = ? ORDER BY id DESC",
        (session["username"],),
    ).fetchall()
    conn.close()
    return render_template("staff_dashboard.html", bookings=bookings, username=session["username"])


@app.route("/staff/update_status/<int:booking_id>", methods=["POST"])
@login_required(role="staff")
def update_status(booking_id):
    new_status = request.form.get("status")
    conn = get_db()
    conn.execute("UPDATE bookings SET status = ? WHERE id = ?", (new_status, booking_id))
    conn.commit()
    conn.close()
    flash("Booking status updated.", "success")
    return redirect(url_for("staff_dashboard"))


# ----------------------------------------------------------------------
# ROUTES - ADMIN
# ----------------------------------------------------------------------
@app.route("/admin/dashboard")
@login_required(role="admin")
def admin_dashboard():
    conn = get_db()
    total_bookings = conn.execute("SELECT COUNT(*) as c FROM bookings").fetchone()["c"]
    total_customers = conn.execute(
        "SELECT COUNT(*) as c FROM users WHERE role = 'customer'"
    ).fetchone()["c"]
    recent_bookings = conn.execute("SELECT * FROM bookings ORDER BY id DESC LIMIT 10").fetchall()

    per_day = conn.execute(
        "SELECT date, COUNT(*) as c FROM bookings GROUP BY date ORDER BY date DESC LIMIT 7"
    ).fetchall()
    chart_labels = [row["date"] for row in reversed(per_day)]
    chart_values = [row["c"] for row in reversed(per_day)]

    this_month = date.today().strftime("%Y-%m")
    revenue_row = conn.execute(
        "SELECT SUM(total_price) as total FROM bookings WHERE date LIKE ?", (f"{this_month}%",)
    ).fetchone()
    revenue_this_month = revenue_row["total"] or 0

    conn.close()

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
    conn = get_db()
    reviews = conn.execute("SELECT * FROM reviews ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("reviews.html", reviews=reviews)


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
init_db()  # runs on import too, so it works under any WSGI server (e.g. PythonAnywhere)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)