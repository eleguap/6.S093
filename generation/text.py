from generation.notion import search_all_pages, collapse_pages
from generation.llm import call_openrouter
from core.models import PostDraft
from pydantic import BaseModel

# Global variables
STRUCTURED_OUTPUT = False

# -------------------- Structured Outputs --------------------
class MastodonPost(BaseModel):
    post_text: str

# -------------------- Mastodon --------------------
def generate_post(corpus = ""):
    if not corpus:
        all_pages = search_all_pages()
        corpus = collapse_pages(all_pages)

    prompt = f"""
        You are a social media assistant.

        Using the following company knowledge, generate a single engaging Mastodon post.
        It should be professional and interesting.

        Knowledge:
        {corpus}
        """

    result = call_openrouter(prompt, STRUCTURED_OUTPUT, MastodonPost)
    if STRUCTURED_OUTPUT:
        text = result.post_text
    else:
        text = result
    text += "\n\n*This post was AI generated.*"

    return PostDraft(
        type="text",
        platform="mastodon",
        original_content=text
    )
