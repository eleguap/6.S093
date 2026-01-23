import os
import requests
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# OpenRouter API Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = os.getenv("OPENROUTER_API_URL")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")
OPENROUTER_STRUCTURED = False

# -------------------- Openrouter --------------------
def call_openrouter(prompt: str, structured: bool, schema: BaseModel = None):
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
