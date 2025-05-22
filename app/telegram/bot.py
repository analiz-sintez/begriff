from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, CallbackContext)
from ..service import (
    get_language, create_word_note, get_views, record_view_start,
    record_answer)
from ..models import db, User

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        "Welcome to the Begriff Bot! "
        "I'll help you learn new words on foreign language.")


def create_bot(token):
    """Start the Telegram bot."""
    application = Application.builder().token(token).build()
    application.bot.initialize()
    application.add_handler(CommandHandler('start', start))
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application
