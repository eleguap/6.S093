import os
import sqlite3
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
DB_FILE = os.getenv("DB_FILE")

def get_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # Posts table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY,
        platform TEXT,
        type TEXT,
        original_content TEXT,
        final_content TEXT,
        image_path TEXT,
        parent_post_id INTEGER,
        status TEXT,
        created_at TEXT,
        posted_at TEXT,
        metadata TEXT,
        img_url TEXT
    )
    """)

    # Feedback table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY,
        post_id INTEGER,
        decision TEXT,
        reason TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()
