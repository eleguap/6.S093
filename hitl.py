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

# async def send_simple_message(text: str):
#     """Send a basic text message to Telegram."""
#     bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
#     message = await bot.send_message(
#         chat_id=int(os.environ["TELEGRAM_CHAT_ID"]),
#         text=text,
#     )
#     print(f"✅ Message sent! ID: {message.message_id}")
#     return message

# async def send_message_with_buttons(text: str):
#     """Send a message with Approve/Reject buttons."""
#     bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])

#     # Create the keyboard with two buttons
#     keyboard = InlineKeyboardMarkup([
#         [
#             InlineKeyboardButton("✅ Approve", callback_data="approve"),
#             InlineKeyboardButton("❌ Reject", callback_data="reject"),
#         ]
#     ])

#     message = await bot.send_message(
#         chat_id=int(os.environ["TELEGRAM_CHAT_ID"]),
#         text=text,
#         reply_markup=keyboard,
#     )
#     print(f"✅ Message with buttons sent! ID: {message.message_id}")
#     return message

# async def send_custom_buttons():
#     """Experiment with different button layouts."""
#     bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])

#     keyboard = InlineKeyboardMarkup([
#         [
#             InlineKeyboardButton("👍 Like", callback_data="like"),
#             InlineKeyboardButton("👎 Dislike", callback_data="dislike"),
#         ],
#         # Add more rows here for vertical arrangement
#         [
#             InlineKeyboardButton("✍️ Edit", callback_data="edit"),
#             InlineKeyboardButton("🔄 Regenerate", callback_data="regenerate"),
#         ]
#     ])

#     await bot.send_message(
#         chat_id=int(os.environ["TELEGRAM_CHAT_ID"]),
#         text="Rate this content:",
#         reply_markup=keyboard,
#     )

# async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Handle button clicks from Telegram."""
#     query = update.callback_query
#     await query.answer()  # Acknowledge the click

#     action = query.data
#     print(f"📥 Button clicked: {action}")

#     if action == "approve":
#         await query.edit_message_text("✅ APPROVED! Post will be published.")
#     elif action == "reject":
#         await query.edit_message_text("❌ REJECTED. Post discarded.")
#     else:
#         await query.edit_message_text(f"Received: {action}")

# async def main():
#     print("🚀 Starting bot... Click a button in Telegram!")

#     app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
#     app.add_handler(CallbackQueryHandler(handle_button_click))

#     # This blocks forever (until Ctrl+C)
#     await app.initialize()
#     await app.start()
#     await app.updater.start_polling()

#     try:
#         await asyncio.Event().wait()
#     except asyncio.CancelledError:
#         pass
#     finally:
#         await app.updater.stop()
#         await app.stop()
#         await app.shutdown()
#         print("\n🛑 Bot stopped.")

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

def post_image_to_mastodon(text):
    url = f"{MASTODON_API_URL}/api/v1/statuses"
    headers = {
        "Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"
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
    hitl(post)
