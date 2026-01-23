from dataclasses import dataclass
from typing import Optional, Literal
from datetime import datetime

@dataclass
class PostDraft:
    type: Literal["text", "image", "reply"]
    platform: str
    original_content: str
    image_path: Optional[str] = None
    parent_post_id: Optional[int] = None
    metadata: dict = None

@dataclass
class Post:
    id: int                        # DB primary key
    platform: str
    type: Literal["text", "image", "reply"]
    original_content: str
    final_content: Optional[str] = None
    image_path: Optional[str] = None
    parent_post_id: Optional[int] = None
    status: str = "generated"
    created_at: datetime = None
    posted_at: Optional[datetime] = None
    metadata: dict = None
    img_url: Optional[str] = None

@dataclass
class Feedback:
    id: int
    post_id: int
    decision: str
    reason: str
    created_at: str
    content: Optional[str] = None
