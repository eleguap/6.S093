import os
import requests
from pydantic import BaseModel
from typing import List
import replicate
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Notion API Configuration
NOTION_API_URL = os.getenv("NOTION_API_URL")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_VERSION = "2022-06-28"
API_BASE = "https://api.notion.com/v1"

# Mastodon API Configuration
MASTODON_API_URL = os.getenv("MASTODON_API_URL")
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN")

# OpenRouter API Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = os.getenv("OPENROUTER_API_URL")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")
OPENROUTER_STRUCTURED = False

REPLICATE_API_KEY = os.getenv("REPLICATE_API_KEY")
os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_KEY
TRIGGER_WORD = "tr1gg3r_w0rd"

# -------------------- Structured Outputs --------------------

class MastodonPost(BaseModel):
    post_text: str

class MastodonReply(BaseModel):
    keyword: str
    replies: List[str]  # exactly 5

# -------------------- Notion --------------------
def search_all_pages():
    url = NOTION_API_URL
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    pages = []
    payload = {
        "page_size": 100  # Max per request
    }
    next_cursor = None

    while True:
        if next_cursor:
            payload["start_cursor"] = next_cursor

        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        # Collect page results
        for result in data.get("results", []):
            if result["object"] == "page":
                pages.append(result)

        if not data.get("has_more"):
            break

        next_cursor = data.get("next_cursor")

    return pages

def get_page_content(page_id):
    url = f"{API_BASE}/blocks/{page_id}/children?page_size=100"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
    }

    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()

def get_all_blocks(block_id):
    blocks = []
    url = f"{API_BASE}/blocks/{block_id}/children?page_size=100"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
    }

    while True:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        for block in data["results"]:
            blocks.append(block)
            if block.get("has_children"):
                blocks.extend(get_all_blocks(block["id"]))

        if not data.get("has_more"):
            break
        url = f"{API_BASE}/blocks/{block_id}/children?start_cursor={data['next_cursor']}"

    return blocks

def block_to_text(block):
    btype = block["type"]
    if btype in block:
        rich = block[btype].get("rich_text", [])
        return "".join(rt["plain_text"] for rt in rich)
    return ""

def read_page_as_text(page_id):
    blocks = get_all_blocks(page_id)
    lines = [block_to_text(b) for b in blocks]
    return "\n".join(l for l in lines if l.strip())

def collapse_pages(all_pages):
    texts = []
    for page in all_pages:
        text = read_page_as_text(page["id"])
        if text.strip():
            texts.append(text)
    return "\n\n".join(texts)


# -------------------- Openrouter --------------------
def call_openrouter(prompt: str, structured, schema: BaseModel = None):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    if structured:
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": schema.model_json_schema()  # pass dict directly
            },
            "temperature": 0.7,
            "max_tokens": 400
        }
    else:
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 400
        }

    resp = requests.post(OPENROUTER_API_URL, headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    if structured:
        return schema.model_validate_json(content)
    return content

# -------------------- Mastodon --------------------
def create_post(all_pages):
    corpus = collapse_pages(all_pages)

    prompt = f"""
        You are a social media assistant.

        Using the following company knowledge, generate a single engaging Mastodon post.
        It should be professional and interesting.
        Always include a disclaimer that this post was AI generated.

        Knowledge:
        {corpus}
        """

    result = call_openrouter(prompt, OPENROUTER_STRUCTURED, MastodonPost)
    if OPENROUTER_STRUCTURED:
        return result.post_text
    return result

def post_to_mastodon(text):
    url = f"{MASTODON_API_URL}/api/v1/statuses"
    headers = {
        "Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"
    }
    payload = {
        "status": text
    }

    resp = requests.post(url, headers=headers, data=payload)
    resp.raise_for_status()
    return resp.json()

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

def reply_to_recent_posts(all_pages):
    corpus = collapse_pages(all_pages)

    prompt = f"""
    You are a social media agent.

    From the following knowledge:
    1. Generate ONE keyword to search on Mastodon.
    2. Generate 5 helpful, relevant replies to recent posts about that keyword.

    Knowledge:
    {corpus}
    """

    result = call_openrouter(prompt, OPENROUTER_STRUCTURED, MastodonReply)
    if human_approve_replies(result.keyword, result.replies):
        statuses = search_mastodon(result.keyword)
        for status, reply in zip(statuses, result.replies):
            reply_to_status(status["id"], reply)
    else:
        print("Replies rejected.")

    return {
        "keyword": result.keyword,
        "replies_sent": len(statuses)
    }

def reply_to_status(status_id, text):
    url = f"{MASTODON_API_URL}/api/v1/statuses"
    headers = {
        "Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"
    }
    payload = {
        "status": text,
        "in_reply_to_id": status_id
    }

    resp = requests.post(url, headers=headers, data=payload)
    resp.raise_for_status()
    return resp.json()

def create_image_post(text = "*This post was AI generated.*"):
    image_path = "my-image.webp"

    try:
        output = replicate.run(
            "sundai-club/redbull_suzuka_livery:24b0b168263d9b15ce91d2e3eeb44958c770602c408a0c947f9d78b8d1fac737",
            input={
                "model": "dev",
                "prompt": f"{TRIGGER_WORD} on track f1",
                "go_fast": False,
                "lora_scale": 1,
                "megapixels": "1",
                "num_outputs": 1,
                "aspect_ratio": "1:1",
                "output_format": "webp",
                "guidance_scale": 3,
                "output_quality": 80,
                "prompt_strength": 0.8,
                "extra_lora_scale": 1,
                "num_inference_steps": 28
            }
        )

        # Download image
        image_url = output[0]
        print("Image URL:", image_url)

        img_resp = requests.get(image_url)
        img_resp.raise_for_status()
        with open(image_path, "wb") as f:
            f.write(img_resp.content)

        # Upload media to Mastodon
        media_url = f"{MASTODON_API_URL}/api/v1/media"
        headers = {
            "Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"
        }

        with open(image_path, "rb") as f:
            files = {"file": f}
            media_resp = requests.post(media_url, headers=headers, files=files)
            media_resp.raise_for_status()

        media_id = media_resp.json()["id"]

        # Create post
        status_url = f"{MASTODON_API_URL}/api/v1/statuses"
        payload = {
            "status": text,
            "media_ids[]": [media_id]
        }

        post_resp = requests.post(status_url, headers=headers, data=payload)
        post_resp.raise_for_status()

        return post_resp.json()

    finally:
        # Always delete local file
        if os.path.exists(image_path):
            os.remove(image_path)

# -------------------- Human --------------------
def human_approve(text):
    print("\n" + "="*60)
    print("PREVIEW:")
    print(text)
    print("="*60)

    while True:
        choice = input("Approve? (y/n): ").strip().lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no"):
            return False

def human_approve_replies(keyword, replies):
    print("\nKeyword:", keyword)
    print("="*60)

    for i, r in enumerate(replies, 1):
        print(f"Reply {i}:")
        print(r)
        print("-"*40)

    while True:
        choice = input("Send these replies? (y/n): ").strip().lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no"):
            return False


if __name__ == "__main__":
    while True:
        print("\nWhat would you like to do?")
        print("1. Create posts from all shared pages in workspace")
        print("2. Reply to recent posts")
        print("3. Create image post")
        print("4. Exit")

        choice = input("\nEnter your choice (1, 2, 3, or 4): ").strip()

        if choice == '1':
            all_pages = search_all_pages()
            post = create_post(all_pages)
            if human_approve(post):
                post_to_mastodon(post)
            else:
                print("Post rejected.")
        elif choice == '2':
            if not OPENROUTER_STRUCTURED:
                print("The free models used to test this does not support structured outputs, so post replying is not available/untested.\n" \
                "If you are using a better model, feel free to set OPENROUTER_STRUCTURED to True and re-run the script to see what happens.")
                continue
            all_pages = search_all_pages()
            reply_to_recent_posts(all_pages)
        elif choice == '3':
            text = input("Input optional text: ")
            if text:
                create_image_post(text)
            else:
                create_image_post()
        elif choice == '4':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")

    # Preview
    # for page in all_pages:
    #     text = read_page_as_text(page["id"])
    #     print("==== PAGE ====")
    #     print(text)  # preview
