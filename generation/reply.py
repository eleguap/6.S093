import os
import db.rag
from fastembed import TextEmbedding
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

# Suppress Hugging Face token warning
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

# Initialize the embedding model (downloads on first use)
embedding_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

# -------------------- Structured Outputs --------------------
class MastodonRagReply(BaseModel):
    post_text: str

# -------------------- Mastodon --------------------
def generate_reply(status):
    status_text = status["content"]  # or ["text"] depending on API
    status_id = status["id"]

    query_embedding = next(embedding_model.embed(status_text))
    rag_results = db.rag.hybrid_search(status_text, query_embedding)

    if not rag_results:
        return None

    knowledge_text = "\n\n".join(
        r["content"] for r in rag_results[:3]
    )

    reply_prompt = f"""
    You are a social media agent.

    Generate a helpful, relevant reply to this post.

    Post:
    {status_text}

    Knowledge:
    {knowledge_text}
    """

    reply_result = call_openrouter(reply_prompt, STRUCTURED_OUTPUT, MastodonRagReply)
    reply_text = reply_result.post_text if STRUCTURED_OUTPUT else reply_result.strip()
    reply_text += "\n\n*This reply was AI generated.*"

    draft = PostDraft(
        type="reply",
        platform="mastodon",
        original_content=reply_text,
        parent_post_id=status_id,
        metadata={"parent_text": status_text}
    )

    return draft
