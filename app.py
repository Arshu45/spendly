from flask import Flask, render_template, request, session, redirect, url_for, abort
from database.db import get_db, init_db, seed_db, get_user_by_email, get_user_by_id, create_user
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-prod"


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        name     = request.form.get("name",     "").strip()
        email    = request.form.get("email",    "").strip()
        password = request.form.get("password", "").strip()

        if not name or not email or not password:
            return render_template(
                "register.html",
                error="All fields are required.",
                name=name, email=email
            )

        if len(password) < 8:
            return render_template(
                "register.html",
                error="Password must be at least 8 characters.",
                name=name, email=email
            )

        if get_user_by_email(email):
            return render_template(
                "register.html",
                error="An account with that email already exists.",
                name=name, email=email
            )

        new_id = create_user(name, email, password)
        session["user_id"] = new_id
        return redirect(url_for("profile"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        email    = request.form.get("email",    "").strip()
        password = request.form.get("password", "").strip()

        if not email or not password:
            return render_template(
                "login.html",
                error="All fields are required.",
                email=email
            )

        user = get_user_by_email(email)
        if not user:
            return render_template(
                "login.html",
                error="Invalid email or password.",
                email=email
            )

        if not check_password_hash(user["password_hash"], password):
            return render_template(
                "login.html",
                error="Invalid email or password.",
                email=email
            )

        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = {
        "name":       "Alex Johnson",
        "email":      "alex@example.com",
        "created_at": "January 2024",
    }
    stats = [
        {"label": "Total Spent",  "value": "$4,250.00", "icon": "credit-card"},
        {"label": "Transactions", "value": "24",        "icon": "receipt"},
        {"label": "Top Category", "value": "Food",      "icon": "tag"},
    ]
    transactions = [
        {"date": "May 20, 2026", "description": "Groceries",        "category": "food",          "amount": "22.75"},
        {"date": "May 15, 2026", "description": "New shoes",         "category": "shopping",      "amount": "89.99"},
        {"date": "May 10, 2026", "description": "Movie tickets",     "category": "entertainment", "amount": "25.00"},
        {"date": "May  8, 2026", "description": "Pharmacy",          "category": "health",        "amount": "35.00"},
        {"date": "May  5, 2026", "description": "Electricity bill",  "category": "bills",         "amount": "120.00"},
        {"date": "May  3, 2026", "description": "Monthly bus pass",  "category": "transport",     "amount": "45.00"},
        {"date": "May  1, 2026", "description": "Lunch at cafe",     "category": "food",          "amount": "12.50"},
    ]
    categories = [
        {"name": "Bills",         "slug": "bills",         "amount": "120.00", "pct": 68},
        {"name": "Shopping",      "slug": "shopping",      "amount": "89.99",  "pct": 51},
        {"name": "Transport",     "slug": "transport",     "amount": "45.00",  "pct": 25},
        {"name": "Health",        "slug": "health",        "amount": "35.00",  "pct": 20},
        {"name": "Food",          "slug": "food",          "amount": "35.25",  "pct": 20},
        {"name": "Entertainment", "slug": "entertainment", "amount": "25.00",  "pct": 14},
    ]
    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


with app.app_context():
    init_db()
    seed_db()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
