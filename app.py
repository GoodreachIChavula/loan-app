from functools import wraps
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"


# -------------------
# DATABASE CONNECTIONN
# -------------------
def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


# -------------------
# DATABASE SETUP
# -------------------
def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        amount REAL,
        interest REAL,
        total REAL,
        balance REAL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER,
        amount REAL
    )
    """)

    # Create admin
    c.execute("SELECT * FROM users WHERE username=?", ("admin",))
    if not c.fetchone():
        hashed_password = generate_password_hash("1234")
        c.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
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
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user"] = user["username"]
            return redirect(url_for("index"))

        return "Invalid credentials"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


# -------------------
# DASHBOARD
# -------------------
@app.route("/")
@login_required
def index():
    conn = get_db_connection()
    c = conn.cursor()

    search = request.args.get("search", "").strip()

    if search:
        c.execute("SELECT * FROM clients WHERE name LIKE ?", (f"%{search}%",))
    else:
        c.execute("SELECT * FROM clients ORDER BY id DESC")

    clients = c.fetchall()

    # Stats
    c.execute("SELECT COALESCE(SUM(amount),0) FROM loans")
    total_loans = c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(amount),0) FROM payments")
    total_collected = c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(balance),0) FROM loans")
    total_balance = c.fetchone()[0]

    profit = total_collected - total_loans

    conn.close()

    return render_template(
        "index.html",
        clients=clients,
        total_loans=total_loans,
        total_collected=total_collected,
        total_balance=total_balance,
        profit=profit
    )


# -------------------
# ADD CLIENT
# -------------------
@app.route("/add_client", methods=["GET", "POST"])
@login_required
def add_client():
    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO clients (name, phone) VALUES (?, ?)", (name, phone))
        conn.commit()
        conn.close()

        return redirect(url_for("index"))

    return render_template("add_client.html")


# -------------------
# ADD LOAN
# -------------------
@app.route("/add_loan", methods=["GET", "POST"])
@login_required
def add_loan():
    conn = get_db_connection()
    c = conn.cursor()

    if request.method == "POST":
        client_id = request.form["client_id"]
        amount = float(request.form["amount"])
        interest = float(request.form["interest"])

        total = amount + (amount * interest / 100)

        c.execute(
            "INSERT INTO loans (client_id, amount, interest, total, balance) VALUES (?, ?, ?, ?, ?)",
            (client_id, amount, interest, total, total)
        )

        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    c.execute("SELECT id, name FROM clients")
    clients = c.fetchall()
    conn.close()

    return render_template("loan.html", clients=clients)


# -------------------
# ADD PAYMENT
# -------------------
@app.route("/add_payment/<int:loan_id>", methods=["GET", "POST"])
@login_required
def add_payment(loan_id):
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("SELECT balance FROM loans WHERE id=?", (loan_id,))
    row = c.fetchone()

    if not row:
        return "Loan not found"

    balance = row[0]

    if request.method == "POST":
        amount = float(request.form["amount"])

        if amount > balance:
            return "Too much payment"

        c.execute("INSERT INTO payments (loan_id, amount) VALUES (?, ?)", (loan_id, amount))
        c.execute("UPDATE loans SET balance = balance - ? WHERE id=?", (amount, loan_id))

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
    app.run(debug=True)