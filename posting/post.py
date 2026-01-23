import os
import requests
import db.posts
from core.models import Post
from google.cloud import storage
from dotenv import load_dotenv

load_dotenv()

# Mastodon API Configuration
MASTODON_API_URL = os.getenv("MASTODON_API_URL")
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN")

# Google Cloud Storage
BUCKET_NAME = "sundai-bucket"

# -------------------- Mastodon --------------------
def upload_image_to_gcloud(local_path: str, destination_blob_name: str) -> str:
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(local_path)
    blob.make_public()
    return blob.public_url

def post_to_mastodon(post: Post):
    headers = {
        "Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"
    }

    media_id = None
    if post.type == "image" and post.image_path:
        media_url = f"{MASTODON_API_URL}/api/v1/media"
        with open(post.image_path, "rb") as img_file:
            files = {"file": img_file}
            media_resp = requests.post(media_url, headers=headers, files=files)
            media_resp.raise_for_status()
            media_id = media_resp.json()["id"]

        gcs_url = upload_image_to_gcloud(post.image_path, os.path.basename(post.image_path))
        post.img_url = gcs_url
        db.posts.update_post_img_url(post.id, gcs_url)

        try:
            os.remove(post.image_path)
        except PermissionError:
            pass

    post_url = f"{MASTODON_API_URL}/api/v1/statuses"
    payload = {
        "status": post.final_content or post.original_content
    }
    if media_id:
        payload["media_ids[]"] = [media_id]
    response = requests.post(post_url, headers=headers, data=payload)
    response.raise_for_status()
    db.posts.update_post_posted_at(post.id)

    return response.json()
