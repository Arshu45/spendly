from flask import Flask, render_template, request, session, redirect, url_for, abort
from database.db import get_db, init_db, seed_db, get_user_by_email, create_user

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
        return redirect(url_for("landing"))

    return render_template("register.html")


@app.route("/login")
def login():
    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


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
