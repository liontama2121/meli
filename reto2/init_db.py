"""
init_db.py
Crea la DB SQLite y un usuario inicial.
Uso:
  python init_db.py --username admin --password tupassword
"""
import argparse
import sqlite3
from passlib.hash import bcrypt

DB = "users.db"

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def add_user(username, password):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    password_hash = bcrypt.hash(password)
    try:
        cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
        conn.commit()
        print(f"User '{username}' created.")
    except Exception as e:
        print("Error:", e)
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    init_db()
    add_user(args.username, args.password)
