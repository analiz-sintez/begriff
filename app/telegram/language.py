import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from datetime import datetime, timedelta, timezone

from telegram.ext import CallbackContext
from telegram.constants import ParseMode

from ..core import get_user
from ..srs import (
    get_language,
    Note,
    View,
    get_notes,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def change_language(update: Update, context: CallbackContext) -> None:
    message_text = update.message.text.strip()
    user = get_user(update.effective_user.username)

    if not message_text.startswith("/language"):
        response_message = (
            "Invalid command format. Use /language <language_name>."
        )
        await update.message.reply_text(
            response_message, parse_mode=ParseMode.MARKDOWN
        )
        return

    language_name = message_text.split("/language", 1)[1].strip()

    if language_name:
        # Setting a language.
        language = get_language(language_name)
        user.set_option("studied_language", language.id)
        response_message = f"Language changed to {language_name}."
        await update.message.reply_text(
            response_message, parse_mode=ParseMode.MARKDOWN
        )
    else:
        # Showing current language with language options to choose
        user_notes = get_notes(user_id=user.id)
        available_languages = {note.language_id for note in user_notes}
        language_buttons = [
            InlineKeyboardButton(
                get_language(lang_id).name,
                callback_data=f"set_language:{lang_id}",
            )
            for lang_id in available_languages
        ]

        response_message = (
            "You study %s now."
            % get_language(user.get_option("studied_language", "English")).name
        )

        if language_buttons:
            response_message += "\n\nChoose a language you want to study:"
            reply_markup = InlineKeyboardMarkup.from_column(language_buttons)
        else:
            response_message += "\n\nYou don't have any notes for other languages. Add notes to get language options."
            reply_markup = None

        await update.message.reply_text(
            response_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )


async def handle_language_change(
    update: Update, context: CallbackContext
) -> None:
    query = update.callback_query
    data = query.data

    if data.startswith("set_language:"):
        language_id = int(data.split(":")[1])
        user = get_user(query.from_user.username)
        language = get_language(language_id)

        user.set_option("studied_language", language.id)
        response_message = f"Language changed to {language.name}."
        await query.answer()
        await query.edit_message_text(
            response_message, parse_mode=ParseMode.MARKDOWN
        )
