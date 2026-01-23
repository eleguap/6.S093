import os
import asyncio
import db.posts
import db.feedback
from core.models import PostDraft, Post
from telegram import Bot
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
from telegram import Update
from telegram.ext import MessageHandler, filters
from dotenv import load_dotenv

load_dotenv()

# Telegram API Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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

async def wait_for_approval_image(img_path: str) -> tuple[str, str | None]:
    """
    Returns:
      ("approve", None)
      ("reject", None)
    """
    global feedback_pending_post, feedback_decision

    async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
        global feedback_decision

        query = update.callback_query
        await query.answer()

        await query.edit_message_reply_markup(reply_markup=None)

        if query.data == "approve":
            feedback_decision = "approve"
            await query.reply_text(f"✅ APPROVED\n\n")
            feedback_done.set()
        elif query.data == "reject":
            feedback_decision = "reject"
            await query.message.reply_text("❌ REJECTED\n\n")

    # Reset state
    feedback_decision = None
    feedback_done.clear()

    # Send the post with buttons
    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data="approve"),
            InlineKeyboardButton("❌ Reject", callback_data="reject"),
        ]
    ])

    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
    caption_text = "📝 New Post for Approval"
    await bot.send_photo(
        chat_id=int(os.environ["TELEGRAM_CHAT_ID"]),
        photo=open(img_path, "rb"),
        caption=caption_text,
        reply_markup=keyboard
    )

    # Set up the listener
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CallbackQueryHandler(handle_button))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Wait for completion
    await feedback_done.wait()

    # Cleanup
    await app.updater.stop()
    await app.stop()
    await app.shutdown()

    return feedback_decision, None


async def wait_for_approval_text(post_content: str, parent_text = str | None) -> tuple[str, str | None]:
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

    message_text = f"📝 New Post for Approval\n\n{post_content}\n\n"
    if parent_text:
        message_text += f"Parent Post: {parent_text}\n\n"

    message_text += f"Characters: {len(post_content)}"
    await bot.send_message(
        chat_id=int(os.environ["TELEGRAM_CHAT_ID"]),
        text=message_text,
        reply_markup=keyboard,
    )

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

def hitl(post: PostDraft) -> Post:
    post_id = db.posts.create_post(post, status="pending")

    if post.type in ["text", "reply"]:
        decision, payload = asyncio.run(wait_for_approval_text(post.original_content, post.metadata.get("parent_text")))
        if decision == "approve":
            db.posts.update_status(post_id, "approved")
        elif decision == "reject":
            db.feedback.create_feedback(post_id=post_id, decision="reject", reason=payload, content=post.original_content)
            db.posts.update_status(post_id, "rejected")
        elif decision == "edit":
            # Update final_content
            db.posts.update_status(post_id, "edited")

    elif post.type == "image":
        decision, _ = asyncio.run(wait_for_approval_image(post.image_path))

        if decision == "approve":
            db.posts.update_status(post_id, "approved")
        elif decision == "reject":
            db.posts.update_status(post_id, "rejected")

    return db.posts.get_post(post_id)
