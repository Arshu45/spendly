# Spec: Registration

## Overview
Implement the registration flow so a new visitor can create a Spendly account.
The `GET /register` route already renders the form; this step adds the `POST /register`
handler that validates input, creates the user record with a hashed password, opens a
session, and redirects the user to the landing page. It also adds the two DB helpers
(`create_user`, `get_user_by_email`) that registration depends on, and configures
`app.secret_key` so Flask sessions work.

## Depends on
- Step 1 — Database Setup (`get_db`, `init_db`, `seed_db`, users table)

## Routes
- `POST /register` — validate form data, create user, set session, redirect — public

> The existing `GET /register` route stays; it must be extended to accept both
> GET and POST via `methods=["GET", "POST"]`.

## Database changes
No new tables or columns. Two new query helpers are needed in `database/db.py`:

| Helper | Signature | Purpose |
|---|---|---|
| `get_user_by_email` | `get_user_by_email(email) → Row \| None` | Duplicate-email check and future login |
| `create_user` | `create_user(name, email, password) → int` | Insert row with hashed password, return new `id` |

## Templates
- **Modify:** `templates/register.html`
  - Fix hardcoded `action="/register"` → `action="{{ url_for('register') }}"`
  - Keep existing `{{ error }}` block for inline error display (no flash needed this step)

- **No new templates.**

## Files to change
| File | What changes |
|---|---|
| `app.py` | Add `app.secret_key`; extend imports (`request`, `session`, `redirect`); merge GET+POST into one route function with POST logic |
| `database/db.py` | Add `get_user_by_email()` and `create_user()` |
| `templates/register.html` | Fix hardcoded action URL |

## Files to create
None.

## New dependencies
No new pip packages. `werkzeug.security.generate_password_hash` is already imported
in `database/db.py`.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterized queries only — never f-strings in SQL
- Hash passwords with `werkzeug.security.generate_password_hash`
- `app.secret_key` must be set before any session usage; use a hard-coded dev string
  (e.g. `"dev-secret-change-in-prod"`) — do NOT read from env or add new packages
- Route function must use `abort()` for unexpected errors, not bare string returns
- Use `url_for()` everywhere in templates — zero hardcoded URL strings
- All templates already extend `base.html`; do not change that

### POST /register logic (ordered)
1. Read `name`, `email`, `password` from `request.form`
2. Strip whitespace; validate all three are non-empty
3. Validate `len(password) >= 8`
4. Call `get_user_by_email(email)` — if a row is returned, re-render the form with
   `error="An account with that email already exists."`
5. Call `create_user(name, email, password)` — this returns the new user's `id`
6. Set `session["user_id"] = <new id>`
7. `redirect(url_for("landing"))`

On any validation failure: re-render `register.html` passing `error=<message>` and
preserve the submitted `name` and `email` values so the user doesn't have to retype.

## Definition of done
- [ ] Submitting valid new-user data creates a row in `users` with a hashed password
- [ ] After successful registration, `session["user_id"]` is set and the user is
      redirected to the landing page
- [ ] Submitting a duplicate email re-renders the form with an error message and does
      not create a second row
- [ ] Submitting with any field empty re-renders the form with an error message
- [ ] Submitting a password shorter than 8 characters re-renders the form with an error
- [ ] Previously typed name and email are preserved in the form on validation error
- [ ] The form `action` uses `url_for('register')` — no hardcoded URL
- [ ] `app.py` has `app.secret_key` set before any route is reached
- [ ] All SQL in `db.py` uses `?` placeholders
