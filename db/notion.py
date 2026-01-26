import os
import re
import hashlib
import requests
from db.schema import get_connection
from db.embedding import generate_embeddings_batch
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Notion API Configuration
NOTION_API_URL = os.getenv("NOTION_API_URL")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_VERSION = "2022-06-28"
API_BASE = "https://api.notion.com/v1"

# Global variables
DIFF_THRESHOLD = 0.25

# -------------------- Hash --------------------
def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# -------------------- Notion --------------------
def search_all_pages():
    url = NOTION_API_URL
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    all_pages = []
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
                all_pages.append(result)

        if not data.get("has_more"):
            break

        next_cursor = data.get("next_cursor")

    return all_pages

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

    if btype in ["heading_1", "heading_2", "heading_3"]:
        rich = block[btype].get("rich_text", [])
        text = "".join(rt["plain_text"] for rt in rich)
        return f"\n## {text}\n"

    if btype in ["paragraph", "bulleted_list_item", "numbered_list_item"]:
        rich = block[btype].get("rich_text", [])
        return "".join(rt["plain_text"] for rt in rich)

    return ""

def read_page_as_text(page_id):
    blocks = get_all_blocks(page_id)
    lines = [block_to_text(b) for b in blocks]
    return "\n".join(l for l in lines if l.strip())

def chunk_document(content: str, filename: str, page_id: str, max_chars: int = 3500, overlap: int = 500):
    sections = re.split(r"\n{2,}", content)

    chunks = []
    current = ""

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # If adding this section exceeds size, flush
        if len(current) + len(section) > max_chars:
            chunks.append(current.strip())
            current = section
        else:
            if current:
                current += "\n\n" + section
            else:
                current = section

    if current.strip():
        chunks.append(current.strip())

    # Add overlap
    final_chunks = []
    for i, chunk in enumerate(chunks):
        if i == 0:
            final_chunks.append(chunk)
        else:
            prev = chunks[i - 1]
            overlap_text = prev[-overlap:]
            final_chunks.append(overlap_text + "\n\n" + chunk)

    # Attach metadata
    results = []
    for i, text in enumerate(final_chunks):
        results.append({
            "content": text,
            "source_type": f"notion_page",
            "source_id": f"{page_id}::chunk_{i}",
            "metadata": {
                "source": filename,
                "chunk_index": i,
                "char_count": len(text),
            }
        })

    return results

def chunk_all_pages(all_pages):
    all_chunks = []

    for page in all_pages:
        page_id = page["id"]
        title = ""
        title_prop = page.get("properties", {}).get("title", {}).get("title", [])
        if title_prop:
            title = title_prop[0].get("plain_text", "")

        text = read_page_as_text(page_id)
        chunks = chunk_document(text, filename=title, page_id=page_id)

        for c in chunks:
            c["metadata"]["page_id"] = page_id
            c["metadata"]["page_title"] = title

        all_chunks.extend(chunks)

    return all_chunks

def sync_notion():
    pages = search_all_pages()
    chunks = chunk_all_pages(pages)

    conn = get_connection()
    cur = conn.cursor()

    # Filter new or updated chunks
    to_embed = []

    for chunk in chunks:
        sid = chunk["source_id"]
        content = chunk["content"]
        new_hash = content_hash(content)

        cur.execute(
            "SELECT content_hash, last_content FROM notion_chunks WHERE source_id = ?",
            (sid,)
        )
        row = cur.fetchone()

        if row is None:
            # New chunk
            cur.execute(
                "INSERT INTO notion_chunks (source_id, content_hash, last_content) VALUES (?, ?, ?)",
                (sid, new_hash, content)
            )

            cur.execute(
                "INSERT INTO notion_triggers (source_id, diff, change_score) VALUES (?, ?, ?)",
                (sid, content, 1.0)
            )

            to_embed.append(chunk)
        else:
            old_hash = row
            if old_hash == new_hash:
                continue  # No change
            # Update canonical record
            cur.execute(
                "UPDATE notion_chunks SET content_hash=?, last_content=?, updated_at=CURRENT_TIMESTAMP WHERE source_id=?",
                (new_hash, content, sid)
            )
            to_embed.append(chunk)

    conn.commit()
    conn.close()

    # Generate and save embeddings for all new/updated chunks
    if to_embed:
        generate_embeddings_batch(to_embed)
