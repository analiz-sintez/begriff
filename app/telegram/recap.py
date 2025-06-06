import logging

from telegram import Update
from telegram.ext import CallbackContext
from telegram.constants import ParseMode

from ..core import get_user
from ..srs import get_language
from ..config import Config
from ..llm import get_recap
from .note import get_notes_to_inject


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def recap_url(update: Update, context: CallbackContext) -> None:
    user_name = update.effective_user.username
    user = get_user(user_name)
    language = get_language(user.get_option("studied_language", "English"))

    notes_to_inject = None
    if "recap" in Config.LLM["inject_notes"]:
        notes_to_inject = get_notes_to_inject(user, language)

    last_line = update.message.text.strip().split("\n")[-1]
    try:
        recap = get_recap(
            last_line,
            language.name,
            notes=notes_to_inject,
        )
        response = f"{recap} [(source)]({last_line})"
    except Exception as e:
        logging.error(f"Got error while recapping: {e}")
        response = "Couldn't process page, possibly it's too large."

    await update.message.reply_text(
        response,
        parse_mode=ParseMode.MARKDOWN,
        reply_to_message_id=update.message.message_id,
    )
