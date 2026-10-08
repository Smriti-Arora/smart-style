"""SQLite accounts and signed-in sessions. Passwords are PBKDF2 hashes; session tokens live in cookies."""
import hashlib
import os
import re
import secrets
import sqlite3
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path=os.path.join(HERE, ".env")):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "1").strip().lower() in ("1", "true", "yes", "on")
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(HERE, "data", "smart_style.db"))
SESSION_DAYS = 30
COOKIE = "ss_session"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _db():
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DATABASE_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    con = _db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS otps (
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            purpose TEXT NOT NULL,
            expires_at REAL NOT NULL,
            PRIMARY KEY (email, purpose)
        );
        """
    )
    con.commit()
    con.close()


def _hash(password):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), 200_000)
    return f"{salt}${dk.hex()}"


def _check(password, stored):
    try:
        salt, hashed = stored.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), 200_000)
    return secrets.compare_digest(dk.hex(), hashed)


def _public(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"]}


def check_email_exists(email):
    email = (email or "").strip().lower()
    if not email:
        return False
    con = _db()
    try:
        row = con.execute("SELECT id, name, email FROM users WHERE email = ?", (email,)).fetchone()
        return bool(row)
    finally:
        con.close()


def register(name, email, password):
    name = (name or "").strip()
    email = (email or "").strip().lower()
    password = password or ""
    if len(name) < 2:
        raise ValueError("Name must be at least 2 characters.")
    if not _EMAIL.match(email):
        raise ValueError("Enter a valid email.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    con = _db()
    try:
        if con.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            raise ValueError("That email is already registered. Sign in or use OTP login instead.")
        cur = con.execute(
            "INSERT INTO users (name, email, password, created_at) VALUES (?, ?, ?, ?)",
            (name, email, _hash(password), time.time()),
        )
        con.commit()
        row = con.execute("SELECT id, name, email FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _public(row)
    finally:
        con.close()


def login(email, password):
    email = (email or "").strip().lower()
    con = _db()
    try:
        row = con.execute("SELECT id, name, email, password FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not _check(password or "", row["password"]):
            raise ValueError("Email or password is wrong.")
        token = secrets.token_hex(24)
        now = time.time()
        con.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, row["id"], now, now + SESSION_DAYS * 86400),
        )
        con.commit()
        return token, _public(row)
    finally:
        con.close()


def generate_otp(email, purpose="login"):
    email = (email or "").strip().lower()
    if not _EMAIL.match(email):
        raise ValueError("Enter a valid email.")
    code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = time.time() + 600  # 10 minutes
    con = _db()
    try:
        con.execute(
            "INSERT OR REPLACE INTO otps (email, code, purpose, expires_at) VALUES (?, ?, ?, ?)",
            (email, code, purpose, expires_at),
        )
        con.commit()
        return code
    finally:
        con.close()


def verify_otp_login(email, code, name="Guest Stylist"):
    email = (email or "").strip().lower()
    code = (code or "").strip()
    con = _db()
    try:
        otp_row = con.execute(
            "SELECT * FROM otps WHERE email = ? AND purpose = 'login' AND code = ? AND expires_at > ?",
            (email, code, time.time()),
        ).fetchone()
        if not otp_row:
            raise ValueError("Invalid or expired OTP code.")
        
        # Invalidate OTP after use
        con.execute("DELETE FROM otps WHERE email = ? AND purpose = 'login'", (email,))

        # Find or auto-create user
        user_row = con.execute("SELECT id, name, email FROM users WHERE email = ?", (email,)).fetchone()
        if not user_row:
            display_name = (name or email.split("@")[0].title()).strip() or "Stylist"
            cur = con.execute(
                "INSERT INTO users (name, email, password, created_at) VALUES (?, ?, ?, ?)",
                (display_name, email, _hash(secrets.token_hex(16)), time.time()),
            )
            user_row = con.execute("SELECT id, name, email FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()

        token = secrets.token_hex(24)
        now = time.time()
        con.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_row["id"], now, now + SESSION_DAYS * 86400),
        )
        con.commit()
        return token, _public(user_row)
    finally:
        con.close()


def reset_password_with_otp(email, code, new_password):
    email = (email or "").strip().lower()
    code = (code or "").strip()
    new_password = new_password or ""
    if len(new_password) < 6:
        raise ValueError("New password must be at least 6 characters.")
    con = _db()
    try:
        otp_row = con.execute(
            "SELECT * FROM otps WHERE email = ? AND purpose = 'reset' AND code = ? AND expires_at > ?",
            (email, code, time.time()),
        ).fetchone()
        if not otp_row:
            raise ValueError("Invalid or expired OTP code.")

        user_row = con.execute("SELECT id, name, email FROM users WHERE email = ?", (email,)).fetchone()
        if not user_row:
            raise ValueError("Account with this email does not exist.")

        con.execute("UPDATE users SET password = ? WHERE id = ?", (_hash(new_password), user_row["id"]))
        con.execute("DELETE FROM otps WHERE email = ? AND purpose = 'reset'", (email,))

        token = secrets.token_hex(24)
        now = time.time()
        con.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_row["id"], now, now + SESSION_DAYS * 86400),
        )
        con.commit()
        return token, _public(user_row)
    finally:
        con.close()


def user_for(token):
    if not token:
        return None
    con = _db()
    try:
        row = con.execute(
            """
            SELECT u.id, u.name, u.email FROM users u
            JOIN sessions s ON s.user_id = u.id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, time.time()),
        ).fetchone()
        return _public(row) if row else None
    finally:
        con.close()


def logout(token):
    if not token:
        return
    con = _db()
    try:
        con.execute("DELETE FROM sessions WHERE token = ?", (token,))
        con.commit()
    finally:
        con.close()
