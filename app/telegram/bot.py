import re
import logging

from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackContext,
)

from . import note, study, note_list, language, recap
from .note import add_notes
from .recap import recap_url
from .router import router


logger = logging.getLogger(__name__)


@router.command("start", "Start using the bot")
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


@router.message("")
async def route_message(update: Update, context: CallbackContext) -> None:
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
    router.attach(application)
    return application
