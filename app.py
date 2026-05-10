from flask import Flask, render_template, request, session, redirect, url_for, abort
from database.db import get_db, init_db, seed_db, get_user_by_email, create_user
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)
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

    uid  = session["user_id"]
    user = get_user_by_id(uid)
    s    = get_summary_stats(uid)
    stats = [
        {"label": "Total Spent",  "value": f"₹{s['total_spent']:,.2f}", "icon": "credit-card"},
        {"label": "Transactions", "value": str(s["transaction_count"]),  "icon": "receipt"},
        {"label": "Top Category", "value": s["top_category"],            "icon": "tag"},
    ]
    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=get_recent_transactions(uid),
        categories=get_category_breakdown(uid),
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
