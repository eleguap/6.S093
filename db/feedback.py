import os
import sqlite3
import datetime
from core.models import Feedback
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
DB_FILE = os.getenv("DB_FILE")

def get_connection():
    return sqlite3.connect(DB_FILE)

def create_feedback(post_id, decision, reason, content):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO feedback (post_id, decision, reason, created_at)
    VALUES (?, ?, ?, ?)
    """, (
        post_id,
        decision,
        reason,
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    feedback_id = cur.lastrowid
    conn.close()

    return Feedback(
        id=feedback_id,
        post_id=post_id,
        decision=decision,
        reason=reason,
        created_at=datetime.utcnow().isoformat(),
        content=content
    )

def get_all_feedback(limit: int = 50, offset: int = 0) -> list[Feedback]:
    """Return a list of Feedback objects, newest first, including content."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT id, post_id, decision, reason, created_at, content
    FROM feedback
    ORDER BY created_at DESC
    LIMIT ? OFFSET ?
    """, (limit, offset))

    rows = cur.fetchall()
    conn.close()

    return [Feedback(*row) for row in rows]


def get_feedback(post_id: int) -> Feedback | None:
    """Return the latest feedback for a given post_id, including content."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT id, post_id, decision, reason, created_at, content
    FROM feedback
    WHERE post_id = ?
    ORDER BY created_at DESC
    LIMIT 1
    """, (post_id,))

    row = cur.fetchone()
    conn.close()

    return Feedback(*row) if row else None
