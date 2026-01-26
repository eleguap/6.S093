# db/state.py
import sqlite3
from db.schema import get_connection

def get(key: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM state WHERE key = ?", (key,))
    row = cur.fetchone()
    return row[0] if row else None

def set(key: str, value: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()
