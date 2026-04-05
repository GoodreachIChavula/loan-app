from functools import wraps
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2

app = Flask(__name__)
app.secret_key = "secret123"

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL is not set!")
    return psycopg2.connect(DATABASE_URL, sslmode='require')


# -------------------
# DATABASE SETUP
# -------------------
def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id SERIAL PRIMARY KEY,
        name TEXT,
        phone TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS loans (
        id SERIAL PRIMARY KEY,
        client_id INTEGER,
        amount REAL,
        interest REAL,
        total REAL,
        balance REAL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        loan_id INTEGER,
        amount REAL
    )
    """)

    # Create admin
    c.execute("SELECT * FROM users WHERE username=%s", ("admin",))
    if not c.fetchone():
        hashed_password = generate_password_hash("1234")
        c.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            ("admin", hashed_password)
        )

    conn.commit()
    conn.close()


# -------------------
# AUTH DECORATOR
# -------------------
def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


# -------------------
# LOGIN
# -------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, username, password FROM users WHERE username=%s", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session["user"] = user[1]
            return redirect(url_for("index"))

        return "Invalid credentials"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


# -------------------
# DASHBOARD
# ----------

@app.route("/")
@login_required
def index():
    conn = get_db_connection()
    c = conn.cursor()

    try:
        c.execute("SELECT * FROM clients ORDER BY id DESC")
        clients = c.fetchall()

        c.execute("SELECT COALESCE(SUM(amount),0) FROM loans")
        total_loans = c.fetchone()[0]

        c.execute("SELECT COALESCE(SUM(amount),0) FROM payments")
        total_collected = c.fetchone()[0]

        c.execute("SELECT COALESCE(SUM(balance),0) FROM loans")
        total_balance = c.fetchone()[0]

        profit = total_collected - total_loans

    except Exception as e:
        conn.close()
        return f"Database error: {e}"

    conn.close()

    return render_template(
        "index.html",
        clients=clients,
        total_loans=total_loans,
        total_collected=total_collected,
        total_balance=total_balance,
        profit=profit
    )# -------------------
# ADD CLIENT
# -------------------
@app.route("/add_client", methods=["GET", "POST"])
@login_required
def add_client():
    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            phone = request.form["phone"].strip()

            conn = get_db_connection()
            c = conn.cursor()
            c.execute("INSERT INTO clients (name, phone) VALUES (%s, %s)", (name, phone))
            conn.commit()
            conn.close()

            return redirect(url_for("index"))

        except Exception as e:
            return f"ERROR: {e}"

    return render_template("add_client.html")# -------------------
# ADD LOAN
# -------------------
@app.route("/add_loan", methods=["GET", "POST"])
@login_required
def add_loan():
    conn = get_db_connection()
    c = conn.cursor()

    if request.method == "POST":
        try:
            client_id = request.form["client_id"]
            amount = float(request.form["amount"])
            interest = float(request.form["interest"])

            total = amount + (amount * interest / 100)

            c.execute(
                "INSERT INTO loans (client_id, amount, interest, total, balance) VALUES (%s, %s, %s, %s, %s)",
                (client_id, amount, interest, total, total)
            )

            conn.commit()
            conn.close()
            return redirect(url_for("index"))

        except Exception as e:
            return f"ERROR: {e}"

    c.execute("SELECT id, name FROM clients")
    clients = c.fetchall()
    conn.close()

    return render_template("loan.html", clients=clients)# -------------------
# ADD PAYMENT
# -------------------
@app.route("/add_payment/<int:loan_id>", methods=["GET", "POST"])
@login_required
def add_payment(loan_id):
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("SELECT balance FROM loans WHERE id=%s", (loan_id,))
    row = c.fetchone()

    if not row:
        return "Loan not found"

    balance = row[0]

    if request.method == "POST":
        amount = float(request.form["amount"])

        if amount > balance:
            return "Too much payment"

        c.execute("INSERT INTO payments (loan_id, amount) VALUES (%s, %s)", (loan_id, amount))
        c.execute("UPDATE loans SET balance = balance - %s WHERE id=%s", (amount, loan_id))

        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    conn.close()
    return render_template("add_payment.html", loan_id=loan_id, balance=balance)


# -------------------
# RUN
# -------------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=10000)