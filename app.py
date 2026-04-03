from functools import wraps
import sqlite3

from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret123"


# -------------------
# DATABASE SETUP
# -------------------
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # USERS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    # CLIENTS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT
    )
    """)

    # LOANS TABLE
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

    # PAYMENTS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER,
        amount REAL
    )
    """)

    # Default admin user
    c.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if c.fetchone() is None:
        hashed_password = generate_password_hash("1234")
        c.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            ("admin", hashed_password)
        )

    conn.commit()
    conn.close()

with app.app_context():
    init_db()

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


# -------------------
# LOGIN / LOGOUT
# -------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
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
# -------------------
@app.route("/", methods=["GET"])
@login_required
def index():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    search = request.args.get("search", "").strip()

    if search:
        c.execute("SELECT * FROM clients WHERE name LIKE ? ORDER BY id DESC", (f"%{search}%",))
    else:
        c.execute("SELECT * FROM clients ORDER BY id DESC")
    clients = c.fetchall()

    c.execute("SELECT SUM(amount) FROM loans")
    total_loans = c.fetchone()[0] or 0

    c.execute("SELECT SUM(amount) FROM payments")
    total_collected = c.fetchone()[0] or 0

    c.execute("SELECT SUM(balance) FROM loans")
    total_balance = c.fetchone()[0] or 0

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
        name = request.form["name"].strip()
        phone = request.form["phone"].strip()

        if not name:
            return "Client name is required"

        conn = sqlite3.connect("database.db")
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
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == "POST":
        client_id = request.form["client_id"].strip()
        amount = float(request.form["amount"])
        interest = float(request.form["interest"])

        c.execute("SELECT id FROM clients WHERE id = ?", (client_id,))
        client = c.fetchone()
        if client is None:
            conn.close()
            return "Client not found"

        total = amount + (amount * interest / 100)

        c.execute(
            "INSERT INTO loans (client_id, amount, interest, total, balance) VALUES (?, ?, ?, ?, ?)",
            (client_id, amount, interest, total, total)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    c.execute("SELECT id, name, phone FROM clients ORDER BY name ASC")
    clients = c.fetchall()
    conn.close()

    return render_template("loan.html", clients=clients)

# -------------------
# VIEW CLIENT LOANS
# -------------------
@app.route("/client/<int:client_id>")
@login_required
def view_client(client_id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
    client = c.fetchone()

    if client is None:
        conn.close()
        return "Client not found", 404

    c.execute("SELECT * FROM loans WHERE client_id = ? ORDER BY id DESC", (client_id,))
    loans = c.fetchall()

    payments = {}
    for loan in loans:
        c.execute("SELECT SUM(amount) FROM payments WHERE loan_id = ?", (loan[0],))
        total_paid = c.fetchone()[0]
        payments[loan[0]] = total_paid if total_paid else 0

    conn.close()

    return render_template("client_loans.html", client=client, loans=loans, payments=payments)


# -------------------
# ADD PAYMENT
# -------------------
@app.route("/add_payment/<int:loan_id>", methods=["GET", "POST"])
@login_required
def add_payment(loan_id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT balance FROM loans WHERE id = ?", (loan_id,))
    row = c.fetchone()

    if row is None:
        conn.close()
        return "Loan not found", 404

    balance = row[0]

    if request.method == "POST":
        amount = float(request.form["amount"])

        if amount <= 0:
            conn.close()
            return "Payment must be greater than zero"

        if amount > balance:
            conn.close()
            return "Error: Payment exceeds remaining balance!"

        c.execute("INSERT INTO payments (loan_id, amount) VALUES (?, ?)", (loan_id, amount))
        c.execute("UPDATE loans SET balance = balance - ? WHERE id = ?", (amount, loan_id))

        conn.commit()
        conn.close()

        return redirect(url_for("index"))

    conn.close()
    return render_template("add_payment.html", loan_id=loan_id, balance=balance)


# -------------------
# RUN APP
# -------------------
if __name__ == "__main__":
    init_db()
    app.run(host='0.0.0.0', port=10000)