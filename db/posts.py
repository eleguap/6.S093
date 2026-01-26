import os
import sqlite3
from datetime import datetime, timezone
from core.models import PostDraft, Post
from db.schema import get_connection

def create_post(draft: PostDraft, status: str = "generated") -> int:
    conn = get_connection()
    cur = conn.cursor()

    now = datetime.now(timezone.utc).isoformat()

    cur.execute("""
        INSERT INTO posts (
            platform, type, original_content, image_path, parent_post_id, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        draft.platform,
        draft.type,
        draft.original_content,
        draft.image_path,
        draft.parent_post_id,
        status,
        now
    ))

    conn.commit()
    post_id = cur.lastrowid
    conn.close()
    return post_id

def get_post(post_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    # Map SQLite row to a dictionary
    keys = ["id", "type", "platform", "original_content", "final_content",
            "image_path", "parent_post_id", "status", "created_at", "posted_at", "metadata",  "img_url"]

    row_dict = dict(zip(keys, row))
    return Post(**row_dict)

def get_all_posts(limit: int = 10, offset: int = 0) -> list[Post]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT *
        FROM posts
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    cursor.execute(query, (limit, offset))
    rows = cursor.fetchall()

    posts = []
    for row in rows:
        post = Post(
            id=row["id"],
            platform=row["platform"],
            type=row["type"],
            original_content=row["original_content"],
            final_content=row["final_content"],
            image_path=row["image_path"],
            parent_post_id=row["parent_post_id"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            posted_at=datetime.fromisoformat(row["posted_at"]) if row["posted_at"] else None,
            metadata=eval(row["metadata"]) if row["metadata"] else {},
            img_url=row["img_url"]
        )
        posts.append(post)

    conn.close()
    return posts

def get_parent_text(post: Post | PostDraft) -> str | None:
    """
    Return the parent post text if this is a reply, or None otherwise.
    """
    if post.type != "reply":
        return None

    # Try metadata first
    if post.metadata and "parent_text" in post.metadata:
        return post.metadata["parent_text"]

    return None

def update_status(post_id: int, status: str):
    conn = get_connection()
    cur = conn.cursor()

    now = datetime.now(timezone.utc).isoformat()

    cur.execute("""
        UPDATE posts
        SET status = ?, decided_at = ?
        WHERE id = ?
    """, (
        status,
        now,
        post_id
    ))

    conn.commit()
    conn.close()

def update_post_img_url(post_id: int, img_url: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE posts SET img_url = ? WHERE id = ?",
        (img_url, post_id)
    )
    conn.commit()
    conn.close()

def update_post_posted_at(post_id: int, posted_at: datetime | None = None):
    posted_at = posted_at or datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE posts SET posted_at = ? WHERE id = ?",
        (posted_at.isoformat(), post_id)
    )
    conn.commit()
    conn.close()
