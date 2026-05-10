import pytest
import sqlite3
from werkzeug.security import generate_password_hash

from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    DEFAULT (datetime('now'))
);
CREATE TABLE expenses (
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

_EXPENSES = [
    (120.00, "Bills",         "2026-05-05", "Electricity bill"),
    (89.99,  "Shopping",      "2026-05-15", "New shoes"),
    (45.00,  "Transport",     "2026-05-03", "Monthly bus pass"),
    (35.00,  "Health",        "2026-05-08", "Pharmacy"),
    (25.00,  "Entertainment", "2026-05-10", "Movie tickets"),
    (22.75,  "Food",          "2026-05-20", "Groceries"),
    (15.00,  "Other",         "2026-05-18", "Miscellaneous"),
    (12.50,  "Food",          "2026-05-01", "Lunch at cafe"),
]


def _build_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)

    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Seeded User", "seeded@test.com", generate_password_hash("pass"), "2026-01-15 10:00:00"),
    )
    seeded_uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [(seeded_uid, amt, cat, dt, desc) for amt, cat, dt, desc in _EXPENSES],
    )

    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Empty User", "empty@test.com", generate_password_hash("pass"), "2026-03-10 09:00:00"),
    )
    empty_uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return seeded_uid, empty_uid


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    seeded_uid, empty_uid = _build_db(db_path)

    def _make_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    monkeypatch.setattr("database.queries.get_db", _make_conn)
    return {"seeded": seeded_uid, "empty": empty_uid}


@pytest.fixture
def client():
    from app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ─── get_user_by_id ────────────────────────────────────────────────────────────

def test_get_user_by_id_valid(db):
    user = get_user_by_id(db["seeded"])
    assert user["name"] == "Seeded User"
    assert user["email"] == "seeded@test.com"
    assert user["member_since"] == "January 2026"


def test_get_user_by_id_nonexistent(db):
    assert get_user_by_id(99999) is None


# ─── get_summary_stats ─────────────────────────────────────────────────────────

def test_get_summary_stats_with_expenses(db):
    stats = get_summary_stats(db["seeded"])
    assert stats["total_spent"] == pytest.approx(365.24, rel=1e-4)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_no_expenses(db):
    stats = get_summary_stats(db["empty"])
    assert stats["total_spent"] == 0
    assert stats["transaction_count"] == 0
    assert stats["top_category"] == "—"


# ─── get_recent_transactions ───────────────────────────────────────────────────

def test_get_recent_transactions_with_expenses(db):
    txs = get_recent_transactions(db["seeded"])
    assert len(txs) == 8
    dates = [tx["date"] for tx in txs]
    assert dates == sorted(dates, reverse=True)
    for tx in txs:
        assert {"date", "description", "category", "amount"} <= tx.keys()


def test_get_recent_transactions_no_expenses(db):
    assert get_recent_transactions(db["empty"]) == []


# ─── get_category_breakdown ────────────────────────────────────────────────────

def test_get_category_breakdown_with_expenses(db):
    cats = get_category_breakdown(db["seeded"])
    assert len(cats) == 7
    amounts = [float(c["amount"]) for c in cats]
    assert amounts == sorted(amounts, reverse=True)
    assert sum(c["pct"] for c in cats) == 100
    for cat in cats:
        assert isinstance(cat["pct"], int)


def test_get_category_breakdown_no_expenses(db):
    assert get_category_breakdown(db["empty"]) == []


# ─── Route: GET /profile ───────────────────────────────────────────────────────

def test_profile_unauthenticated(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_profile_authenticated(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    resp = client.get("/profile")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "₹" in body
    assert "365.24" in body
    assert "Bills" in body
