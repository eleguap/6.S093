import os
import json
import asyncio
import requests
import social_agent
import image_agent
from pathlib import Path
from telegram import Bot
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
from telegram import Update
from telegram.ext import MessageHandler, filters
from dotenv import load_dotenv

load_dotenv()

# Feedback filepath
FEEDBACK_FILE = Path("feedback.json")

# Telegram API Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Mastodon API Configuration
MASTODON_API_URL = os.getenv("MASTODON_API_URL")
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN")

os.environ["TELEGRAM_BOT_TOKEN"] = TELEGRAM_BOT_TOKEN
os.environ["TELEGRAM_CHAT_ID"] = TELEGRAM_CHAT_ID

# -------------------- Telegram --------------------
feedback_pending_post = None
feedback_decision = None
feedback_reason = None
feedback_edited_post = None

waiting_for_reason = False
waiting_for_edit = False

feedback_done = asyncio.Event()

async def wait_for_approval(post_content: str) -> str:
    """
    Returns:
      ("approve", None)
      ("reject", reason)
      ("edit", edited_post)
    """
    global feedback_pending_post, feedback_decision, feedback_reason, feedback_edited_post, waiting_for_reason, waiting_for_edit

    async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
        global feedback_decision, waiting_for_reason, waiting_for_edit

        query = update.callback_query
        await query.answer()

        await query.edit_message_reply_markup(reply_markup=None)

        if query.data == "approve":
            feedback_decision = "approve"
            await query.edit_message_text(f"✅ APPROVED\n\n{feedback_pending_post}")
            feedback_done.set()
        elif query.data == "reject":
            feedback_decision = "reject"
            waiting_for_reason = True
            waiting_for_edit = False
            await query.message.reply_text(
                "❌ REJECTED\n\n"
                "Please reply with the reason for rejection.\n"
                "This feedback helps improve future posts.\n\n"
                "Examples: 'Too promotional' or 'Wrong tone'"
            )
        elif query.data == "edit":
            feedback_decision = "edit"
            waiting_for_edit = True
            waiting_for_reason = False
            await query.edit_message_text(
                "✏️ EDIT MODE\n\n"
                "Please reply with the *edited version* of the post.\n\n"
                "You can copy the text below and modify it."
            )
            await query.message.reply_text(feedback_pending_post)


    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        global feedback_reason, feedback_edited_post
        global waiting_for_reason, waiting_for_edit

        text = update.message.text

        if waiting_for_reason:
            feedback_reason = text

            if FEEDBACK_FILE.exists() and FEEDBACK_FILE.stat().st_size > 0:
                with open(FEEDBACK_FILE, "r") as f:
                    data = json.load(f)
            else:
                data = {}

            key = feedback_reason.lower().strip()
            data[key] = data.get(key, 0) + 1

            with open(FEEDBACK_FILE, "w") as f:
                json.dump(data, f, indent=2)

            waiting_for_reason = False
            await update.message.reply_text(
                f"📝 Feedback recorded!\n\nReason: {feedback_reason}"
            )
            feedback_done.set()
        elif waiting_for_edit:
            feedback_edited_post = text
            waiting_for_edit = False

            await update.message.reply_text(
                f"✏️ Edit received! Using the new version:\n\n{feedback_edited_post}"
            )
            feedback_done.set()

    # Reset state
    feedback_pending_post = post_content
    feedback_decision = None
    feedback_reason = None
    feedback_edited_post = None
    waiting_for_reason = False
    waiting_for_edit = False
    feedback_done.clear()

    # Send the post with buttons
    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data="approve"),
            InlineKeyboardButton("❌ Reject", callback_data="reject"),
            InlineKeyboardButton("✏️ Edit", callback_data="edit")
        ]
    ])

    await bot.send_message(
        chat_id=int(os.environ["TELEGRAM_CHAT_ID"]),
        text=f"📝 New Post for Approval\n\n{post_content}\n\nCharacters: {len(post_content)}",
        reply_markup=keyboard,
    )
    print("📱 Sent to Telegram. Waiting for approval...")

    # Set up the listener
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Wait for completion
    await feedback_done.wait()

    # Cleanup
    await app.updater.stop()
    await app.stop()
    await app.shutdown()

    if feedback_decision == "edit":
        return "edit", feedback_edited_post
    elif feedback_decision == "reject":
        return "reject", feedback_reason
    else:
        return "approve", None

# -------------------- Mastodon --------------------
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

def post_image_to_mastodon(text, image_path):
    media_url = f"{MASTODON_API_URL}/api/v1/media"
    headers = {
        "Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"
    }

    with open(image_path, "rb") as img_file:
        files = {"file": img_file}
        media_resp = requests.post(media_url, headers=headers, files=files)
        media_resp.raise_for_status()
        media_id = media_resp.json()["id"]

    try:
        os.remove(image_path)
    except PermissionError:
        print(f"Warning: Could not delete {image_path}, it may be open in another program.")

    post_url = f"{MASTODON_API_URL}/api/v1/statuses"
    data = {
        "status": text,
        "media_ids[]": [media_id]
    }

    resp = requests.post(post_url, headers=headers, data=data)
    resp.raise_for_status()

    return resp.json()

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

def hitl(post):
    if post["type"] == "post":
        text = post["payload"]

        decision, payload = asyncio.run(wait_for_approval(text))

        print(f"\n📊 Result: {decision}")
        if decision == "approve":
            post_to_mastodon(text)
        elif decision == "reject" and payload:
            print(f"\n💡 Feedback to improve the prompt:")
            print(f"   The human said: '{payload}'")
            print(f"   Consider adjusting your prompt to avoid this issue.")
        elif decision == "edit":
            print("New post:", payload)

    elif post["type"] == "image":
        text, image_path = post["payload"]
        print(f"\n Text: {text}")
        print(f"\n🖼️ Image ready: {image_path}")
        choice = input("Post this image? (Y/N): ").strip().lower()
        if choice == "y":
            post_image_to_mastodon(text, image_path)

    elif post["type"] == "replies":
        statuses, replies = post["payload"]
        for status, reply in zip(statuses, replies):
            print(f"\n💬 Original post: {status['content']}")
            print(f"Suggested reply: {reply}")
            choice = input("Send this reply? (Y/N): ").strip().lower()
            if choice == "y":
                reply_to_status(status["id"], reply)


if __name__ == "__main__":
    post = social_agent.generate_post()
    # post = image_agent.generate_image_post()
    hitl(post)
