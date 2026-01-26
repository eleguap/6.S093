import os
import re
import httpx
import asyncio
import db.schema
import db.notion
import db.state
import db.posts
import db.feedback
from db.triggers import get_pending_triggers, mark_trigger_processed
import generation.text
import generation.image
import generation.replies
import generation.reply
import hitl.hitl
import posting.post

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Mastodon API Configuration
MASTODON_API_URL = os.getenv("MASTODON_API_URL")
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN")

# Initialize database
db.schema.init_db()

# -------------------- Notion Polling --------------------
async def sync_notion_loop():
    while True:
        db.notion.sync_notion()
        await asyncio.sleep(15 * 60)

async def process_notion_triggers_loop():
    while True:
        triggers = get_pending_triggers()

        if not triggers:
            await asyncio.sleep(15 * 60)
            continue

        additions = [t["diff"] for t in triggers]

        draft = generation.text.generate_post(additions)
        post = hitl.hitl(draft)
        if post.status != "rejected":
            posting.post(post)

        for t in triggers:
            mark_trigger_processed(t["id"])

        await asyncio.sleep(15 * 60)

# -------------------- Mastodon Polling --------------------
def strip_html(html):
    return re.sub("<.*?>", "", html)

async def handle_mention(notification, client):
    status = notification["status"]

    reply_text = generation.reply.generate_reply(status)
    if reply_text is None:
        return
    post = hitl.hitl(reply_text)
    posting.post(post)

last_seen_id = db.state.get("mastodon_last_seen")
async def poll_mastodon():
    global last_seen_id
    headers = {"Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"}

    async with httpx.AsyncClient() as client:
        while True:
            params = {}
            if last_seen_id:
                params["since_id"] = last_seen_id

            r = await client.get(
                f"{MASTODON_API_URL}/api/v1/notifications",
                headers=headers,
                params=params
            )
            notifs = r.json()

            for n in reversed(notifs):
                last_seen_id = n["id"]
                db.state.set("mastodon_last_seen", last_seen_id)

                if n["type"] == "mention":
                    await handle_mention(n, client)

            await asyncio.sleep(15)

# -------------------- Lifespan --------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    mastodon_task = asyncio.create_task(poll_mastodon())
    notion_sync_task = asyncio.create_task(sync_notion_loop())
    trigger_task = asyncio.create_task(process_notion_triggers_loop())
    yield
    mastodon_task.cancel()
    notion_sync_task.cancel()
    trigger_task.cancel()

# -------------------- App --------------------
app = FastAPI(
    title="Social Media Agent API",
    lifespan=lifespan
)

# -------------------- Pydantic Models --------------------
class FeedbackRequest(BaseModel):
    post_id: int
    decision: str  # approve, reject, edit
    reason: Optional[str] = None
    edited_content: Optional[str] = None

class ImageRequest(BaseModel):
    prompt: Optional[str] = None
    text: Optional[str] = None

class ReplyRequest(BaseModel):
    keyword: Optional[str] = None

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Social Media Agent API",
        "endpoints": {
            "posts": "/posts",
            "text": "/text",
            "image": "/image",
            "replies": "/replies",
            "feedback": "/feedback",
            "stats": "/stats"
        }
    }

# -------------------- Posts Endpoints --------------------
@app.get("/posts")
async def get_posts(limit: int = 50, offset: int = 0):
    """Get all posts"""
    posts = db.posts.get_all_posts(limit, offset)

    return {
        "count": len(posts),
        "limit": limit,
        "offset": offset,
        "posts": posts
    }

@app.get("/posts/{post_id}")
async def get_post(post_id: int):
    """Get a specific post"""
    post = db.posts.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    return post

# -------------------- Text Endpoints --------------------
@app.post("/text/generate")
async def generate_post():
    """Generate a new image post"""
    try:
        # Generate post using social_agent
        draft = generation.text.generate_image_post()
        post = hitl.hitl(draft)
        if post.status != "rejected":
            posting.post(post)

        return {
            "success": True,
            "post_id": post.post_id,
            "status": post.status,
            "content": post.final_content or post.original_content,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------- Image Endpoints --------------------
@app.post("/image/generate")
async def generate_post():
    """Generate a new post"""
    try:
        # Generate post using social_agent
        draft = generation.image.generate_post()
        post = hitl.hitl(draft)
        if post.status != "rejected":
            posting.post(post)

        return {
            "success": True,
            "post_id": post.post_id,
            "status": post.status,
            "content": post.img_url,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------- Replies Endpoints --------------------
@app.post("/replies/generate")
async def generate_post():
    """Generate a new post"""
    try:
        # Generate post using social_agent
        drafts = generation.replies.generate_replies()
        post_ids = []
        statuses = []
        posts = []

        for draft in drafts:
            post = hitl.hitl(draft)
            if post.status != "rejected":
                posting.post(post)
            post_ids.append(post.post_id)
            statuses.append(post.status)
            posts.append(post.final_content or post.original_content)

        return {
            "success": True,
            "post_id": post_ids,
            "status": statuses,
            "content": posts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------- Feedback Endpoints --------------------
@app.get("/feedback")
async def get_feedbacks(limit: int = 50, offset: int = 0):
    """Get all feedback"""
    feedback_records = db.feedback.get_all_feedback(limit, offset)

    return {
        "count": len(feedback_records),
        "limit": limit,
        "offset": offset,
        "feedback": feedback_records
    }

@app.get("/feedback/{post_id}")
async def get_feedback(post_id: int):
    """Get all feedback"""
    feedback = db.feedback.get_feedback(post_id)

    return feedback
