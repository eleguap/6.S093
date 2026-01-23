import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Notion API Configuration
NOTION_API_URL = os.getenv("NOTION_API_URL")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_VERSION = "2022-06-28"
API_BASE = "https://api.notion.com/v1"

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
