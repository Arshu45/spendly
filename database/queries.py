from datetime import datetime
from database.db import get_db


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    dt = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": dt.strftime("%B %Y"),
    }


def get_summary_stats(user_id):
    conn = get_db()
    agg = conn.execute(
        "SELECT COALESCE(SUM(amount), 0.0) AS total, COUNT(*) AS cnt"
        " FROM expenses WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    top = conn.execute(
        "SELECT category FROM expenses WHERE user_id = ?"
        " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return {
        "total_spent": agg["total"],
        "transaction_count": agg["cnt"],
        "top_category": top["category"] if top else "—",
    }


def get_recent_transactions(user_id, limit=10):
    conn = get_db()
    rows = conn.execute(
        "SELECT date, description, category, amount FROM expenses"
        " WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [
        {
            "date": r["date"],
            "description": r["description"],
            "category": r["category"],
            "amount": f"{r['amount']:.2f}",
        }
        for r in rows
    ]


def get_category_breakdown(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT category, SUM(amount) AS total FROM expenses"
        " WHERE user_id = ? GROUP BY category ORDER BY total DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    if not rows:
        return []
    grand_total = sum(r["total"] for r in rows)
    exact = [r["total"] / grand_total * 100 for r in rows]
    floors = [int(p) for p in exact]
    remainder = 100 - sum(floors)
    # Largest-remainder: distribute extra points to categories with biggest fractional parts
    by_frac = sorted(range(len(rows)), key=lambda i: exact[i] - floors[i], reverse=True)
    for i in range(remainder):
        floors[by_frac[i]] += 1
    return [
        {
            "name": rows[i]["category"],
            "slug": rows[i]["category"].lower(),
            "amount": f"{rows[i]['total']:.2f}",
            "pct": floors[i],
        }
        for i in range(len(rows))
    ]
