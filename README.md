# Smart Salon & Parlour (SQLite Edition)

Full-stack Flask app using:
- **SQLite** — database (`salon.db`, created automatically, no setup needed)
- **Custom auth** — Werkzeug password hashing, no external service
- **Local folder (`static/uploads`)** — booking reference image uploads
- **EmailJS** — emails the chosen staff member the moment a booking is confirmed
  (runs in the browser, needs internet on the visitor's device)
- **fpdf2** — downloadable invoice as PDF

This version needs **no external API** for login/booking/database, so it runs
on fully free hosts (like PythonAnywhere's free tier) without any restrictions.

## 1. EmailJS setup (staff booking notification)

1. Create a free account at https://www.emailjs.com
2. **Email Services** → Add a service (e.g. connect your Gmail) → copy the **Service ID**.
3. **Email Templates** → Create a template using these variables in the body:
   `{{staff_name}}`, `{{staff_email}}`, `{{customer_name}}`, `{{services}}`, `{{date}}`, `{{time}}`, `{{seat}}`
   → set "To email" to `{{staff_email}}` → copy the **Template ID**.
4. **Account → General** → copy your **Public Key**.

Open `static/js/config.js` and fill in:
```js
const EMAILJS_PUBLIC_KEY = "...";
const EMAILJS_SERVICE_ID = "...";
const EMAILJS_TEMPLATE_ID = "...";
```

## 2. Run locally (VS Code)

```
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## 3. Run in Pydroid 3 (Android)

1. Copy the whole `smart_salon` folder onto your phone.
2. Pydroid 3 → Pip → install `flask`, `fpdf2`.
3. Open `app.py` → Run.
4. Open the browser at `http://127.0.0.1:5000`.

## 4. Deploy for free, 24/7, no card — PythonAnywhere

1. Go to https://www.pythonanywhere.com → **Create a Beginner account** (free, no card).
2. Once logged in, go to **Files** tab → upload your project folder
   (or use **Consoles → Bash** and `git clone` your GitHub repo).
3. Go to **Web** tab → **Add a new web app** → choose **Flask** → Python 3.10.
4. Set the source code path to your project folder, and edit the generated
   `WSGI configuration file` so it points to your `app.py`'s `app` object:
   ```python
   import sys
   path = '/home/yourusername/smart_salon'
   if path not in sys.path:
       sys.path.append(path)
   from app import app as application
   ```
5. Go to **Consoles → Bash** and run:
   ```
   pip install --user -r /home/yourusername/smart_salon/requirements.txt
   ```
6. Go back to the **Web** tab → click **Reload**.
7. Your app is live at `https://yourusername.pythonanywhere.com` — 24/7, free,
   no sleep mode, no card required.

## Default logins

| Role     | Email                       | Password    |
|----------|------------------------------|-------------|
| Admin    | navamuthu2007@gmail.com      | Salon@123   |
| Staff 1  | staff1@gmail.com             | Salon@123   |
| Staff 2  | staff2@gmail.com             | Salon@123   |
| Staff 3  | staff3@gmail.com             | Salon@123   |
| Staff 4  | staff4@gmail.com             | Salon@123   |
| Customer | (register your own account) | —           |

These are auto-created in `salon.db` the first time the app runs.

## Password rules (register / forgot password)

Every password must have: at least 6 characters, one uppercase letter, one
lowercase letter, one number, and one special symbol (e.g. `Salon@123`).

## Forgot Password

Since there's no external email service on the backend, "Forgot Password"
lets someone who knows the registered email set a new password directly
(matches the original "no real email sending" requirement). For a real
production launch where security matters more, consider adding an OTP or
email-verification step before allowing the reset.

## Notes

- Booking IDs are generated automatically as `SSP-0001`, `SSP-0002`, etc.
- Prices for invoices/totals use a fixed value per service (the midpoint of
  each displayed price range) — edit the `SERVICES` dictionary in `app.py`
  to change prices.
- Role is detected automatically at registration: the admin email and the
  4 staff emails are hard-coded; everyone else becomes a `customer`.