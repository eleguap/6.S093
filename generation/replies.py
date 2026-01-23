import os
import requests
from generation.notion import search_all_pages, collapse_pages
from generation.llm import call_openrouter
from core.models import PostDraft
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Mastodon API Configuration
MASTODON_API_URL = os.getenv("MASTODON_API_URL")
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN")

# Global variables
STRUCTURED_OUTPUT = False

# -------------------- Structured Outputs --------------------
class MastodonSearch(BaseModel):
    keyword: str

class MastodonReply(BaseModel):
    post_text: str

# -------------------- Mastodon --------------------
def search_mastodon(keyword):
    url = f"{MASTODON_API_URL}/api/v2/search"
    headers = {
        "Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"
    }
    params = {
        "q": keyword,
        "type": "statuses",
        "limit": 5
    }

    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()["statuses"]

def generate_replies():
    all_pages = search_all_pages()
    corpus = collapse_pages(all_pages)

    keyword_prompt = f"""
    You are a social media agent.

    From the following knowledge:
    Generate ONE relevant keyword to search on Mastodon.

    Only return the keyword.

    Knowledge:
    {corpus}
    """

    keyword_result = call_openrouter(
        keyword_prompt,
        STRUCTURED_OUTPUT,
        MastodonSearch
    )

    if STRUCTURED_OUTPUT:
        keyword = keyword_result.keyword
    else:
        keyword = keyword_result.strip()

    statuses = search_mastodon(keyword)
    drafts = []

    for status in statuses:
        status_text = status["content"]  # or ["text"] depending on API
        status_id = status["id"]

        reply_prompt = f"""
        You are a social media agent.

        Generate a helpful, relevant reply to this post.

        Post:
        {status_text}

        Knowledge:
        {corpus}
        """

        reply_result = call_openrouter(reply_prompt, STRUCTURED_OUTPUT, MastodonReply)
        reply_text = reply_result.post_text if STRUCTURED_OUTPUT else reply_result.strip()
        reply_text += "\n\n*This reply was AI generated.*"

        draft = PostDraft(
            type="reply",
            platform="mastodon",
            original_content=reply_text,
            parent_post_id=status_id,
            metadata={"parent_text": status_text}
        )

        drafts.append(draft)

    return drafts
