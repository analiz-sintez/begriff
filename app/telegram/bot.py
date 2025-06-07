import re
import logging

from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler,
)

from .note import add_notes, get_notes_to_inject
from .study import study_next_card, handle_study_session
from .note_list import list_cards
from .language import change_language, handle_language_change
from .recap import recap_url


logger = logging.getLogger(__name__)


async def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message to the user when they start the bot.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    logger.info("User %s started the bot.", update.effective_user.id)
    await update.message.reply_text(
        """
Welcome to the Begriff Bot! I'll help you learn new words in a foreign language.
        
Here are the commands you can use:
Simply enter words separated by a newline to add them to your study list with automatic explanations.
/list - See all the words you've added to your study list along with their details.
/study - Start a study session with your queued words.
"""
    )


def __is_note_format(text: str) -> bool:
    """
    Check if every line in the input text is in the format suitable for notes.
    """
    lines = text.strip().split("\n")
    return all(re.match(r".{1,32}(?::.*)?", line.strip()) for line in lines)


async def router(update: Update, context: CallbackContext) -> None:
    """Route the input text to the appropriate handler.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """

    text = update.message.text
    url_pattern = re.compile(r"https?://\S+")
    last_line = text.strip().split("\n")[-1]
    if url_pattern.match(last_line):
        await recap_url(update, context)
    elif __is_note_format(text):
        await add_notes(update, context)
    else:
        await process_text(update, context)


async def process_text(update: Update, context: CallbackContext) -> None:
    """Process longer text input.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    # This function will handle longer text inputs
    pass


def create_bot(token: str) -> Application:
    """
    Create and configure the Telegram bot application
    with command and callback handlers.

    Args:
        token: The bot token for authentication.

    Returns:
        A configured Application instance representing the bot.
    """
    application = Application.builder().token(token).build()

    # Define bot commands for the menu
    commands = [
        BotCommand("start", "Start using the bot"),
        BotCommand("study", "Start a study session"),
        BotCommand("list", "List all your words"),
        BotCommand("language", "Change studied language"),
    ]

    async def set_commands(application):
        await application.bot.set_my_commands(commands)

    application.post_init = set_commands

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("study", study_next_card))
    application.add_handler(CommandHandler("list", list_cards))
    application.add_handler(CommandHandler("language", change_language))

    # MessageHandler for adding words or processing input by default
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, router)
    )

    # CallbackQueryHandler for inline button responses
    application.add_handler(
        CallbackQueryHandler(handle_language_change, pattern=r"^set_language:")
    )
    application.add_handler(
        CallbackQueryHandler(handle_study_session, pattern=r"^(answer|grade):")
    )

    return application
