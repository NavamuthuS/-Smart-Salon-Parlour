# Smart Salon & Parlour (Firebase Edition)

Full-stack Flask app using:
- **Firestore** — database (users, bookings, reviews)
- **Firebase Authentication** — login / register
- **Local folder (`static/uploads`)** — booking reference image uploads (free, no Blaze plan needed)
- **EmailJS** — emails the chosen staff member the moment a booking is confirmed

## 1. Firebase setup

1. Go to https://console.firebase.google.com → create a project.
2. **Authentication** → Sign-in method → enable **Email/Password**.
3. **Firestore Database** → Create database (start in test mode is fine for development).
4. **Project settings (gear icon) → General** → scroll to "Your apps" → note your **Web API Key**.
5. **Project settings → Service accounts** → Generate new private key → downloads a `serviceAccountKey.json` file.
   - Put that file directly inside the `smart_salon` folder (same level as `app.py`).

Open `app.py` and fill in the top config section:

```python
FIREBASE_WEB_API_KEY = "PASTE_YOUR_FIREBASE_WEB_API_KEY_HERE"
```

(`FIREBASE_SERVICE_ACCOUNT_KEY` already points at `serviceAccountKey.json` in the project folder — no edit needed if you placed the file there.)

> Note: Firebase Storage now requires the paid Blaze plan, so this app keeps
> booking reference images on the local `static/uploads` folder instead —
> everything else (database + auth) stays on the free Spark plan.

## 2. EmailJS setup (staff booking notification)

1. Create a free account at https://www.emailjs.com
2. **Email Services** → Add a service (e.g. connect your Gmail) → copy the **Service ID**.
3. **Email Templates** → Create a template using these variables in the body:
   `{{staff_name}}`, `{{staff_email}}`, `{{customer_name}}`, `{{services}}`, `{{date}}`, `{{time}}`, `{{seat}}`
   → set the "To email" field of the template to `{{staff_email}}` → copy the **Template ID**.
4. **Account → General** → copy your **Public Key**.

Open `static/js/config.js` and fill in:

```js
const EMAILJS_PUBLIC_KEY = "...";
const EMAILJS_SERVICE_ID = "...";
const EMAILJS_TEMPLATE_ID = "...";
```

That's it — no server-side email credentials needed. As soon as a customer confirms
a booking, the browser calls EmailJS directly and the selected staff member
(staff1–staff4) gets an email with the customer's name, services, date, time and seat.

## 3. Run in VS Code

```
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## 4. Run in Pydroid 3 (Android)

1. Copy the whole `smart_salon` folder (including `serviceAccountKey.json`) onto your phone.
2. Pydroid 3 → Pip → install `flask`, `firebase-admin`, `requests`.
3. Open `app.py` → Run.
4. Open the browser at `http://127.0.0.1:5000`.

(Internet connection is required since Firestore/Auth are cloud services.)

## Default logins

| Role     | Email                       | Password |
|----------|------------------------------|----------|
| Admin    | navamuthu2007@gmail.com      | 12345678 |
| Staff 1  | staff1@gmail.com             | 12345678 |
| Staff 2  | staff2@gmail.com             | 12345678 |
| Staff 3  | staff3@gmail.com             | 12345678 |
| Staff 4  | staff4@gmail.com             | 12345678 |
| Customer | (register your own account) | —        |

These are auto-created in Firebase Auth + Firestore the first time `app.py` runs
(`seed_default_users()`).

## 5. Deploy to the internet (Render.com — free)

1. Push this whole folder to a **GitHub repository** (private is fine).
   `.gitignore` already excludes `serviceAccountKey.json` and other secrets —
   never commit that file.
2. Go to https://render.com → sign up with GitHub → **New + → Web Service**.
3. Connect your repository. Fill in:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app` (already set via the `Procfile`)
4. Under **Environment**, add these variables:
   - `FIREBASE_SERVICE_ACCOUNT_JSON` → paste the **entire contents** of your
     `serviceAccountKey.json` file (open it in a text editor, copy everything).
   - `FIREBASE_WEB_API_KEY` → your Firebase Web API Key.
   - `FLASK_SECRET_KEY` → any random long string (e.g. `super-secret-2026-xyz`).
5. Click **Create Web Service**. In 2-3 minutes you'll get a live link like:
   `https://smart-salon-parlour.onrender.com`

Note: Render's free tier "sleeps" after 15 minutes of no traffic and takes
~30 seconds to wake up on the next visit — normal for the free plan.

## Notes

- Booking reference images are stored in `static/uploads/` (created automatically) —
  this stays on Firebase's free Spark plan since Storage isn't used.
- Role is still detected automatically at registration: the admin email and the
  4 staff emails are hard-coded; everyone else becomes a `customer`.