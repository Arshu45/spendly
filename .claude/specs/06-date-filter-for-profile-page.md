# Spec: Date Filter For Profile Page

## Overview
Step 6 adds a date range filter to the profile page so users can scope all
displayed data — summary stats, transaction list, and category breakdown — to
a specific time window. Without this filter every user sees lifetime totals,
which becomes less useful as expenses accumulate. The filter is driven by two
optional query-string parameters (`from` and `to`) and defaults to the current
calendar month when neither is supplied. The profile route, the three query
helpers, and the profile template are all updated; no new routes or tables are
needed.

## Depends on
- Step 1: Database setup (`expenses` table with `date` TEXT column exists)
- Step 2: Registration (users stored in DB)
- Step 3: Login / Logout (`session["user_id"]` set on login)
- Step 4: Profile page static UI (template structure already in place)
- Step 5: Backend routes for profile page (query helpers in `database/queries.py` exist)

## Routes
No new routes. The existing `GET /profile` route is modified to accept optional
query parameters:
- `?from=YYYY-MM-DD` — start of the date range (inclusive)
- `?to=YYYY-MM-DD`   — end of the date range (inclusive)

When neither parameter is present, the route defaults to the first and last day
of the current calendar month.

## Database changes
No database changes. The `expenses.date` TEXT column (format `YYYY-MM-DD`)
already supports range queries via SQLite string comparison.

## Templates
- **Modify**: `templates/profile.html`
  - Add a filter form above the stats section with two `<input type="date">`
    fields (`from_date` and `to_date`) and a "Filter" submit button.
  - The inputs must be pre-populated with the active `from_date` and `to_date`
    values passed from the route so the selected range is visible after submit.
  - All four sections (stats, transactions, category breakdown) already render
    from Jinja variables — no structural changes needed beyond the form.

## Files to change
- `app.py` — update `profile()` to read `from` and `to` query params, default
  to current month, validate format, and pass them to all three query helpers.
- `database/queries.py` — update `get_summary_stats`, `get_recent_transactions`,
  and `get_category_breakdown` to accept optional `date_from` and `date_to`
  keyword arguments and add `WHERE date BETWEEN ? AND ?` clauses when supplied.
- `templates/profile.html` — add the filter form (described above).

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- `date BETWEEN ? AND ?` uses SQLite string comparison which is correct for
  ISO-8601 `YYYY-MM-DD` dates — no date casting needed
- The filter form must use `method="GET"` so the selected range is bookmarkable
  and reflected in the URL
- `from` and `to` are reserved Python keywords — use `date_from` / `date_to`
  as Python variable names; the HTML inputs must be named `from` and `to` to
  keep URLs conventional (`?from=...&to=...`)
- Default range (current month) must be computed in the route, not hardcoded
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- If either query param is present but malformed (not `YYYY-MM-DD`), silently
  fall back to the current-month default rather than raising a 400 error
- `get_user_by_id` does not need date filtering — do not change its signature

## Definition of done
- [ ] Visiting `/profile` with no query params shows data for the current calendar month only
- [ ] Selecting a custom date range and clicking "Filter" reloads the page with `?from=...&to=...` in the URL
- [ ] The `from` and `to` date inputs are pre-filled with the active filter range after submit
- [ ] Summary stats (total spent, transaction count, top category) reflect only expenses within the selected range
- [ ] Transaction list shows only expenses within the selected range, still ordered newest-first
- [ ] Category breakdown reflects only expenses within the selected range; percentages still sum to 100 %
- [ ] Selecting a range with no expenses shows ₹0.00, 0 transactions, and an empty category breakdown — no errors
- [ ] Selecting a range that spans multiple months works correctly
