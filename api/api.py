import fastapi
import uvicorn
import db.schema
import db.posts
import db.feedback
import generation.text
import generation.image
import generation.replies
import hitl.hitl
import posting.post

from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional

app = fastapi.FastAPI(title="Social Media Agent API")

# Initialize database
db.schema.init_db()

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

# -------------------- Stats Endpoints --------------------
@app.get("/stats/feedback")
async def get_feedback_stats():
    """Get feedback statistics"""

    return {
        "result": "unimplemented"
    }

# -------------------- Main --------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
