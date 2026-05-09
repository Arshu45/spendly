# Spec: Login and Logout

## Overview
Implement the login and logout flows so an existing Spendly user can authenticate
and end their session. The `GET /login` route already renders the form; this step
adds the `POST /login` handler that validates credentials against the database,
opens a session on success, and returns an error on failure. It also converts the
`GET /logout` stub into a real route that clears the session and redirects to the
landing page. After this step, the full auth cycle (register → login → logout) is
operational.

## Depends on
- Step 1 — Database Setup (`get_db`, `users` table, `get_user_by_email`)
- Step 2 — Registration (`create_user`, `session["user_id"]`, `app.secret_key`)

## Routes
- `POST /login` — validate email + password, set session, redirect to landing — public
- `GET /logout` — clear session, redirect to landing — logged-in (no hard guard yet)

> The existing `GET /login` route must be extended to accept both GET and POST
> via `methods=["GET", "POST"]`.

## Database changes
No new tables or columns.

One new query helper is needed in `database/db.py`:

| Helper | Signature | Purpose |
|---|---|---|
| `get_user_by_id` | `get_user_by_id(user_id) → Row \| None` | Load the logged-in user's full record by primary key |

`get_user_by_email` already exists and will be reused for the login credential check.

## Templates
- **Modify:** `templates/login.html`
  - Ensure the form `action` uses `{{ url_for('login') }}` (not a hardcoded URL)
  - Ensure `method="post"` is set on the form
  - Add an `{{ error }}` display block (matching the pattern in `register.html`)
  - Preserve the submitted `email` value on validation failure

- **No new templates.**

## Files to change
| File | What changes |
|---|---|
| `app.py` | Extend `login` to handle POST; implement `logout`; import `check_password_hash` |
| `database/db.py` | Add `get_user_by_id()` |
| `templates/login.html` | Fix form action, add error display, preserve email on failure |

## Files to create
None.

## New dependencies
No new pip packages. `werkzeug.security.check_password_hash` is already available
via the installed `werkzeug` package.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterized queries only — never f-strings in SQL
- Verify passwords with `werkzeug.security.check_password_hash`
- Use a single generic error message for both bad email and bad password
  (`"Invalid email or password."`) — never reveal which field was wrong
- Use `url_for()` everywhere in templates — zero hardcoded URL strings
- All templates already extend `base.html`; do not change that
- Use CSS variables — never hardcode hex values in any new CSS
- `logout` must call `session.clear()` (not `session.pop`) to wipe all session data

### POST /login logic (ordered)
1. Read `email` and `password` from `request.form`
2. Strip whitespace; validate both are non-empty — re-render form with error if not
3. Call `get_user_by_email(email)` — if no row returned, re-render with
   `error="Invalid email or password."` (do not hint which field failed)
4. Call `check_password_hash(user["password_hash"], password)` — if it returns
   `False`, re-render with the same generic error message
5. Set `session["user_id"] = user["id"]`
6. `redirect(url_for("landing"))`

On any validation failure: re-render `login.html` passing `error=<message>` and
preserve the submitted `email` value so the user does not have to retype it.

### GET /logout logic
1. Call `session.clear()`
2. `redirect(url_for("landing"))`

## Definition of done
- [ ] Submitting valid credentials sets `session["user_id"]` and redirects to landing
- [ ] Submitting an unknown email re-renders the form with a generic error and does
      not expose whether the email exists
- [ ] Submitting a correct email but wrong password re-renders with the same generic
      error message
- [ ] Submitting with either field empty re-renders with an error message
- [ ] The submitted email value is preserved in the form on validation error
- [ ] Visiting `/logout` clears the session and redirects to the landing page
- [ ] The login form `action` uses `url_for('login')` — no hardcoded URL
- [ ] All SQL in `db.py` uses `?` placeholders
- [ ] No new pip packages are installed
