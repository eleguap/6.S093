import os
import sqlite3
import sqlite_vec
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
DB_FILE = os.getenv("DB_FILE")

def get_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_connection()
    conn.row_factory = sqlite3.Row

    # Load sqlite-vec extension
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

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

    # Metadata table (stores content and metadata, linked to vectors by rowid)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS embeddings_meta (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,
        source_id TEXT,
        content TEXT NOT NULL,
        metadata TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Vector table using sqlite-vec (384 dimensions for MiniLM-L6-v2)
    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS vec_embeddings USING vec0(
        embedding float[384] distance_metric=cosine
    )
    """)

    # FTS5 virtual table for BM25 keyword search
    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS embeddings_fts USING fts5(
        content,
        source_type,
        source_id,
        content='embeddings_meta',
        content_rowid='id'
    )
    """)

    # Triggers to keep FTS5 in sync with embeddings_meta table
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS embeddings_ai AFTER INSERT ON embeddings_meta BEGIN
        INSERT INTO embeddings_fts(rowid, content, source_type, source_id)
        VALUES (new.id, new.content, new.source_type, new.source_id);
    END
    """)

    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS embeddings_ad AFTER DELETE ON embeddings_meta BEGIN
        INSERT INTO embeddings_fts(embeddings_fts, rowid, content, source_type, source_id)
        VALUES ('delete', old.id, old.content, old.source_type, old.source_id);
    END
    """)

    # Mastodon states
    cur.execute("""
    CREATE TABLE IF NOT EXISTS state (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Notion tabes
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notion_chunks (
        source_id TEXT PRIMARY KEY,
        content_hash TEXT NOT NULL,
        last_content TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS notion_triggers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id TEXT,
        diff TEXT,
        change_score REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        used INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()
