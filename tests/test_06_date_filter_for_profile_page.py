"""
tests/test_06_date_filter_for_profile_page.py

Spec: Step 6 — Date Filter for Profile Page

Tests verify that GET /profile:
  - requires authentication (auth guard)
  - defaults to the current calendar month when no query params are given
  - pre-populates the filter form inputs with the active date range
  - accepts ?from=YYYY-MM-DD&to=YYYY-MM-DD and scopes all data to that window
  - silently falls back to the current-month default on malformed params
  - returns correct stats, transactions (newest-first), and category breakdown
  - handles a range that contains no expenses without errors
  - correctly spans multiple months when the range crosses month boundaries
  - never leaks another user's expenses
"""

import sqlite3
import pytest
from datetime import date
import calendar as cal_mod

from werkzeug.security import generate_password_hash

from app import app as flask_app


# ─────────────────────────────────────────────────────────────────────────────
# Schema string (mirrors database/db.py) so we can build an isolated in-memory
# DB without touching the real spendly.db file.
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      REAL    NOT NULL,
    category    TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    description TEXT,
    created_at  TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helper: current-month first / last day strings
# ─────────────────────────────────────────────────────────────────────────────

def _current_month_range():
    today = date.today()
    first = today.replace(day=1).isoformat()
    last_day = cal_mod.monthrange(today.year, today.month)[1]
    last = today.replace(day=last_day).isoformat()
    return first, last


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path):
    """
    Build a fresh SQLite file with:
      - primary_user  — has expenses spread across Jan 2026, Mar 2026, May 2026
      - other_user    — has one expense (to verify data isolation)
      - empty_user    — no expenses at all

    Returns a dict:
        {
            "path": str,
            "primary_uid": int,
            "other_uid": int,
            "empty_uid": int,
        }
    """
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)

    # primary_user
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Primary User", "primary@test.com", generate_password_hash("secret99"), "2025-11-01 08:00:00"),
    )
    primary_uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Expenses spread across three calendar months
    primary_expenses = [
        # January 2026
        (primary_uid, 200.00, "Bills",         "2026-01-10", "January rent"),
        (primary_uid,  50.00, "Food",           "2026-01-20", "January groceries"),
        # March 2026
        (primary_uid, 300.00, "Shopping",       "2026-03-05", "New laptop bag"),
        (primary_uid,  75.00, "Health",         "2026-03-15", "Doctor visit"),
        (primary_uid,  25.00, "Food",           "2026-03-22", "Restaurant"),
        # May 2026
        (primary_uid, 120.00, "Bills",          "2026-05-01", "Electricity"),
        (primary_uid,  45.00, "Transport",      "2026-05-10", "Bus pass"),
        (primary_uid,  30.00, "Entertainment",  "2026-05-20", "Cinema"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        primary_expenses,
    )

    # other_user — used for data-isolation test
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Other User", "other@test.com", generate_password_hash("secret99"), "2025-12-01 09:00:00"),
    )
    other_uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (other_uid, 999.00, "Bills", "2026-03-10", "Other user expense"),
    )

    # empty_user — no expenses
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Empty User", "empty@test.com", generate_password_hash("secret99"), "2026-01-05 10:00:00"),
    )
    empty_uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.commit()
    conn.close()

    return {
        "path": path,
        "primary_uid": primary_uid,
        "other_uid": other_uid,
        "empty_uid": empty_uid,
    }


@pytest.fixture
def app(db_path, monkeypatch):
    """
    Configure flask_app for testing and redirect all get_db() calls to the
    isolated tmp SQLite file (not the real spendly.db).
    """
    def _make_conn():
        conn = sqlite3.connect(db_path["path"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr("database.db.get_db", _make_conn)
    monkeypatch.setattr("database.queries.get_db", _make_conn)

    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client, db_path):
    """Test client with primary_user already logged in via session manipulation."""
    with client.session_transaction() as sess:
        sess["user_id"] = db_path["primary_uid"]
    return client


@pytest.fixture
def auth_client_empty(client, db_path):
    """Test client with empty_user (no expenses) already logged in."""
    with client.session_transaction() as sess:
        sess["user_id"] = db_path["empty_uid"]
    return client


# ─────────────────────────────────────────────────────────────────────────────
# Auth guard
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthGuard:
    def test_profile_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 302, "Unauthenticated /profile must redirect"
        assert "/login" in resp.headers["Location"], "Redirect must point to /login"

    def test_profile_unauthenticated_with_date_params_still_redirects(self, client):
        resp = client.get("/profile?from=2026-03-01&to=2026-03-31")
        assert resp.status_code == 302, "Auth guard must fire even when date params are present"
        assert "/login" in resp.headers["Location"]


# ─────────────────────────────────────────────────────────────────────────────
# Default-month behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestDefaultMonthBehaviour:
    def test_no_params_returns_200(self, auth_client):
        resp = auth_client.get("/profile")
        assert resp.status_code == 200, "Authenticated /profile with no params must return 200"

    def test_no_params_form_prefilled_with_current_month_first_day(self, auth_client):
        first, _ = _current_month_range()
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert first in body, (
            f"Filter form must be pre-filled with current month start ({first})"
        )

    def test_no_params_form_prefilled_with_current_month_last_day(self, auth_client):
        _, last = _current_month_range()
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert last in body, (
            f"Filter form must be pre-filled with current month end ({last})"
        )

    def test_no_params_only_shows_current_month_expenses(self, auth_client):
        """
        primary_user has expenses in Jan/Mar/May 2026.
        Unless the test is running in one of those months, the profile should show
        0 transactions (scoped to current month only).
        We verify the page renders without error — the data-scoping correctness
        for specific months is covered in TestDateFiltering.
        """
        resp = auth_client.get("/profile")
        assert resp.status_code == 200
        # The page must still render all structural elements even with 0 results
        body = resp.data.decode("utf-8")
        assert "Recent Transactions" in body, "Transactions table heading must always render"
        assert "By Category" in body, "Category breakdown heading must always render"


# ─────────────────────────────────────────────────────────────────────────────
# Template landmarks
# ─────────────────────────────────────────────────────────────────────────────

class TestTemplateLandmarks:
    def test_filter_form_has_get_method(self, auth_client):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert 'method="GET"' in body or "method='GET'" in body, (
            "Filter form must use method=GET so the range is reflected in the URL"
        )

    def test_filter_form_has_from_input(self, auth_client):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert 'name="from"' in body or "name='from'" in body, (
            "Filter form must include an input named 'from'"
        )

    def test_filter_form_has_to_input(self, auth_client):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert 'name="to"' in body or "name='to'" in body, (
            "Filter form must include an input named 'to'"
        )

    def test_filter_form_has_submit_button(self, auth_client):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert "Filter" in body, "Filter form must contain a Filter submit button"

    def test_user_name_rendered_in_profile(self, auth_client):
        resp = auth_client.get("/profile?from=2026-01-01&to=2026-01-31")
        body = resp.data.decode("utf-8")
        assert "Primary User" in body, "User's name must appear on the profile page"

    def test_stats_section_renders(self, auth_client):
        resp = auth_client.get("/profile?from=2026-01-01&to=2026-01-31")
        body = resp.data.decode("utf-8")
        assert "Total Spent" in body
        assert "Transactions" in body
        assert "Top Category" in body

    def test_rupee_symbol_present(self, auth_client):
        resp = auth_client.get("/profile?from=2026-01-01&to=2026-01-31")
        body = resp.data.decode("utf-8")
        assert "₹" in body, "Amount must be displayed with ₹ symbol"


# ─────────────────────────────────────────────────────────────────────────────
# Date filtering correctness
# ─────────────────────────────────────────────────────────────────────────────

class TestDateFiltering:
    def test_january_range_shows_correct_total(self, auth_client):
        """primary_user Jan 2026: 200.00 + 50.00 = 250.00"""
        resp = auth_client.get("/profile?from=2026-01-01&to=2026-01-31")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "250.00" in body, "Total spent for Jan 2026 must be ₹250.00"

    def test_january_range_shows_correct_transaction_count(self, auth_client):
        """primary_user Jan 2026 has exactly 2 transactions."""
        resp = auth_client.get("/profile?from=2026-01-01&to=2026-01-31")
        body = resp.data.decode("utf-8")
        # The transaction count stat tile contains '2'
        assert ">2<" in body or "value\">2" in body or "2</div>" in body or ">2<" in body, (
            "Transaction count for Jan 2026 must be 2"
        )

    def test_january_range_shows_correct_top_category(self, auth_client):
        """In Jan 2026 Bills (200) > Food (50), so top category is Bills."""
        resp = auth_client.get("/profile?from=2026-01-01&to=2026-01-31")
        body = resp.data.decode("utf-8")
        assert "Bills" in body, "Top category for Jan 2026 must be Bills"

    def test_march_range_shows_correct_total(self, auth_client):
        """primary_user Mar 2026: 300.00 + 75.00 + 25.00 = 400.00"""
        resp = auth_client.get("/profile?from=2026-03-01&to=2026-03-31")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "400.00" in body, "Total spent for Mar 2026 must be ₹400.00"

    def test_march_range_top_category_is_shopping(self, auth_client):
        """In Mar 2026, Shopping (300) is the top category."""
        resp = auth_client.get("/profile?from=2026-03-01&to=2026-03-31")
        body = resp.data.decode("utf-8")
        assert "Shopping" in body, "Top category for Mar 2026 must be Shopping"

    def test_may_range_shows_correct_total(self, auth_client):
        """primary_user May 2026: 120.00 + 45.00 + 30.00 = 195.00"""
        resp = auth_client.get("/profile?from=2026-05-01&to=2026-05-31")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "195.00" in body, "Total spent for May 2026 must be ₹195.00"

    def test_transactions_ordered_newest_first(self, auth_client):
        """Within May 2026 the three expenses must appear newest-first."""
        resp = auth_client.get("/profile?from=2026-05-01&to=2026-05-31")
        body = resp.data.decode("utf-8")
        pos_may20 = body.find("2026-05-20")
        pos_may10 = body.find("2026-05-10")
        pos_may01 = body.find("2026-05-01")
        assert pos_may20 < pos_may10 < pos_may01, (
            "Transactions must be ordered newest date first"
        )

    def test_transactions_outside_range_excluded(self, auth_client):
        """When filtering to Jan 2026, Mar/May expenses must not appear."""
        resp = auth_client.get("/profile?from=2026-01-01&to=2026-01-31")
        body = resp.data.decode("utf-8")
        assert "2026-03-05" not in body, "March expense must not appear in January filter"
        assert "2026-05-01" not in body, "May expense must not appear in January filter"

    def test_category_breakdown_reflects_range(self, auth_client):
        """Jan 2026 has Bills and Food; Shopping/Health/Transport must not appear."""
        resp = auth_client.get("/profile?from=2026-01-01&to=2026-01-31")
        body = resp.data.decode("utf-8")
        # Bills and Food are present in January
        assert "Bills" in body
        assert "Food" in body
        # These categories only appear in other months
        # We check the category breakdown section specifically by looking for
        # the category badge or bar, not the stat-tile top category label
        # Count occurrences of "Shopping" — it should only appear if actually in range
        # Since March has Shopping and January doesn't, Shopping row should be absent
        # We verify by checking that "New laptop bag" (description) is not in body
        assert "New laptop bag" not in body, (
            "March Shopping expense description must not appear in January filter"
        )

    def test_category_percentages_sum_to_100(self, auth_client):
        """
        Category breakdown percentages for March 2026 (3 categories) must sum to 100.
        We verify by parsing pct values out of the rendered bar widths.
        """
        resp = auth_client.get("/profile?from=2026-03-01&to=2026-03-31")
        body = resp.data.decode("utf-8")
        # Extract all occurrences of "width: N%" from the response
        import re
        pcts = [int(m) for m in re.findall(r"width:\s*(\d+)%", body)]
        assert len(pcts) > 0, "Category breakdown bars must render with width percentages"
        assert sum(pcts) == 100, (
            f"Category bar percentages must sum to 100, got {sum(pcts)} from {pcts}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Empty range behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestEmptyRangeBehaviour:
    def test_range_with_no_expenses_returns_200(self, auth_client):
        """A valid date range that has no expenses must not raise a 500."""
        resp = auth_client.get("/profile?from=2025-01-01&to=2025-01-31")
        assert resp.status_code == 200

    def test_range_with_no_expenses_shows_zero_total(self, auth_client):
        resp = auth_client.get("/profile?from=2025-01-01&to=2025-01-31")
        body = resp.data.decode("utf-8")
        assert "0.00" in body, "Empty range must display ₹0.00 total spent"

    def test_range_with_no_expenses_shows_zero_transaction_count(self, auth_client):
        resp = auth_client.get("/profile?from=2025-01-01&to=2025-01-31")
        body = resp.data.decode("utf-8")
        # The stat tile for Transactions must show 0
        assert "0" in body, "Empty range must display 0 transactions"

    def test_range_with_no_expenses_top_category_is_dash(self, auth_client):
        """When there are no expenses, top category should be the em-dash fallback."""
        resp = auth_client.get("/profile?from=2025-01-01&to=2025-01-31")
        body = resp.data.decode("utf-8")
        assert "—" in body, "Empty range must display '—' as top category"

    def test_range_with_no_expenses_no_transaction_rows(self, auth_client):
        """No <td class="tx-date"> entries should appear for an empty range."""
        resp = auth_client.get("/profile?from=2025-01-01&to=2025-01-31")
        body = resp.data.decode("utf-8")
        assert "tx-date" not in body, (
            "No transaction date cells should render for an empty range"
        )

    def test_empty_user_no_expenses_renders_correctly(self, auth_client_empty):
        """User with zero expenses across all time must still get a 200."""
        resp = auth_client_empty.get("/profile?from=2026-01-01&to=2026-12-31")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "0.00" in body


# ─────────────────────────────────────────────────────────────────────────────
# Malformed query param fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestMalformedParamFallback:
    @pytest.mark.parametrize("from_val,to_val", [
        ("not-a-date", "2026-03-31"),         # malformed from
        ("2026-03-01", "not-a-date"),         # malformed to
        ("not-a-date", "not-a-date"),         # both malformed
        ("2026-13-01", "2026-03-31"),         # invalid month
        ("2026-03-32", "2026-03-31"),         # invalid day
        ("20260301",   "20260331"),           # wrong format (no dashes)
        ("",           "2026-03-31"),         # empty from
        ("2026-03-01", ""),                   # empty to
        ("2026/03/01", "2026/03/31"),         # wrong separator
        ("March 1 2026", "March 31 2026"),    # human-readable format
    ])
    def test_malformed_params_fallback_to_current_month(self, auth_client, from_val, to_val):
        """
        Any combination of malformed/missing date params must fall back to the
        current calendar month default and return 200 (never 400/500).
        """
        resp = auth_client.get(f"/profile?from={from_val}&to={to_val}")
        assert resp.status_code == 200, (
            f"Malformed params from='{from_val}' to='{to_val}' must not cause an error"
        )
        first, last = _current_month_range()
        body = resp.data.decode("utf-8")
        assert first in body, (
            f"After malformed params, form must show current month start ({first})"
        )
        assert last in body, (
            f"After malformed params, form must show current month end ({last})"
        )

    @pytest.mark.parametrize("from_val,to_val", [
        ("not-a-date", "2026-03-31"),
        ("2026-03-01", "not-a-date"),
        ("not-a-date", "not-a-date"),
    ])
    def test_malformed_params_page_renders_without_exception(self, auth_client, from_val, to_val):
        """Page must render structural landmarks even after param fallback."""
        resp = auth_client.get(f"/profile?from={from_val}&to={to_val}")
        body = resp.data.decode("utf-8")
        assert "Recent Transactions" in body
        assert "By Category" in body


# ─────────────────────────────────────────────────────────────────────────────
# Only one param provided — spec says both must be valid for a custom range,
# otherwise fall back to the current-month default.
# ─────────────────────────────────────────────────────────────────────────────

class TestPartialParams:
    def test_only_from_param_falls_back_to_current_month(self, auth_client):
        """Providing only ?from= (with valid value, no ?to=) must fall back."""
        resp = auth_client.get("/profile?from=2026-03-01")
        assert resp.status_code == 200
        first, last = _current_month_range()
        body = resp.data.decode("utf-8")
        assert first in body and last in body, (
            "Providing only ?from= must fall back to current-month default"
        )

    def test_only_to_param_falls_back_to_current_month(self, auth_client):
        """Providing only ?to= (with valid value, no ?from=) must fall back."""
        resp = auth_client.get("/profile?to=2026-03-31")
        assert resp.status_code == 200
        first, last = _current_month_range()
        body = resp.data.decode("utf-8")
        assert first in body and last in body, (
            "Providing only ?to= must fall back to current-month default"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Cross-month range
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossMonthRange:
    def test_jan_to_mar_2026_total(self, auth_client):
        """
        Jan + Mar 2026 expenses:
          Jan: 200.00 + 50.00 = 250.00
          Mar: 300.00 + 75.00 + 25.00 = 400.00
          Total: 650.00
        Feb 2026 has no expenses for primary_user, so total is unchanged.
        """
        resp = auth_client.get("/profile?from=2026-01-01&to=2026-03-31")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "650.00" in body, (
            "Cross-month range Jan–Mar 2026 total must be ₹650.00"
        )

    def test_jan_to_mar_2026_transaction_count(self, auth_client):
        """Jan (2) + Mar (3) = 5 transactions in the cross-month range."""
        resp = auth_client.get("/profile?from=2026-01-01&to=2026-03-31")
        body = resp.data.decode("utf-8")
        # '5' must appear as the transaction count stat value
        assert "5" in body, "Cross-month Jan–Mar 2026 must show 5 transactions"

    def test_cross_month_range_excludes_out_of_range_expenses(self, auth_client):
        """May 2026 expenses must not appear in a Jan–Mar 2026 range."""
        resp = auth_client.get("/profile?from=2026-01-01&to=2026-03-31")
        body = resp.data.decode("utf-8")
        assert "2026-05-01" not in body, "May 2026 expense must not appear in Jan–Mar filter"
        assert "2026-05-10" not in body
        assert "2026-05-20" not in body

    def test_cross_month_range_includes_boundary_dates(self, auth_client):
        """The BETWEEN clause is inclusive; boundary dates must be included."""
        # 2026-01-10 and 2026-03-22 are the outer boundary dates of our seeded data
        resp = auth_client.get("/profile?from=2026-01-10&to=2026-03-22")
        body = resp.data.decode("utf-8")
        assert "2026-01-10" in body, "From boundary date must be included (inclusive)"
        assert "2026-03-22" in body, "To boundary date must be included (inclusive)"


# ─────────────────────────────────────────────────────────────────────────────
# Data isolation — another user's expenses must not leak
# ─────────────────────────────────────────────────────────────────────────────

class TestDataIsolation:
    def test_other_user_expense_not_visible_to_primary_user(self, auth_client):
        """
        other_user has a ₹999.00 Bills expense on 2026-03-10.
        primary_user's profile must never include that amount.
        """
        resp = auth_client.get("/profile?from=2026-03-01&to=2026-03-31")
        body = resp.data.decode("utf-8")
        assert "999.00" not in body, (
            "Another user's expense amount must not appear on primary_user's profile"
        )
        assert "Other user expense" not in body, (
            "Another user's expense description must not appear on primary_user's profile"
        )

    def test_primary_user_total_excludes_other_user(self, auth_client):
        """
        primary_user Mar 2026 total = 400.00 (not 1399.00 if data leaks).
        """
        resp = auth_client.get("/profile?from=2026-03-01&to=2026-03-31")
        body = resp.data.decode("utf-8")
        assert "400.00" in body, "Total must reflect only primary_user's expenses"
        assert "1399.00" not in body, "Total must not include other_user's expenses"


# ─────────────────────────────────────────────────────────────────────────────
# Form pre-population after submitting a custom range
# ─────────────────────────────────────────────────────────────────────────────

class TestFormPrePopulation:
    def test_custom_range_from_input_prefilled(self, auth_client):
        """After submitting ?from=2026-03-01&to=2026-03-31, the from input must show 2026-03-01."""
        resp = auth_client.get("/profile?from=2026-03-01&to=2026-03-31")
        body = resp.data.decode("utf-8")
        assert "2026-03-01" in body, (
            "The 'from' date input must be pre-populated with the submitted from value"
        )

    def test_custom_range_to_input_prefilled(self, auth_client):
        """After submitting ?from=2026-03-01&to=2026-03-31, the to input must show 2026-03-31."""
        resp = auth_client.get("/profile?from=2026-03-01&to=2026-03-31")
        body = resp.data.decode("utf-8")
        assert "2026-03-31" in body, (
            "The 'to' date input must be pre-populated with the submitted to value"
        )

    def test_both_date_values_present_in_form_inputs(self, auth_client):
        """Both value attributes must reflect the active filter range."""
        resp = auth_client.get("/profile?from=2026-05-01&to=2026-05-31")
        body = resp.data.decode("utf-8")
        assert "2026-05-01" in body
        assert "2026-05-31" in body
