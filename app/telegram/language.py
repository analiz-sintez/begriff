import logging
from typing import Optional
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import CallbackContext

from ..core import get_user
from ..srs import get_language, get_notes
from .utils import send_message
from .router import router


logger = logging.getLogger(__name__)


@router.command(
    "language",
    args=["language_name", "native_language_name"],
    description="Change studied language",
)
async def change_language(
    update: Update,
    context: CallbackContext,
    language_name: Optional[str] = None,
    native_language_name: Optional[str] = None,
) -> None:
    user = get_user(update.effective_user.username)

    if language_name:
        # Setting a language.
        language = get_language(language_name)
        user.set_option("studied_language", language.id)
        response_message = f"Language changed to {language_name}."

        if native_language_name and not native_language_name == language_name:
            # Setting native language for this language.
            native_language = get_language(native_language_name)
            user.set_option(
                f"languages/{language.id}/native_language", native_language.id
            )
            response_message += (
                f"\n\nNative language for studying {language_name} "
                f"set to {native_language_name}. "
                f"All explanations will be in {native_language_name}. "
                f"To retain explanations in {language_name}, just pass it "
                f"as native language: /language {language_name} {language_name}."
            )

        await send_message(update, context, response_message)

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
            keyboard = InlineKeyboardMarkup.from_column(language_buttons)
        else:
            response_message += "\n\nYou don't have any notes for other languages. Add notes to get language options."
            keyboard = None

        await send_message(update, context, response_message, keyboard)


@router.callback_query("^set_language:(?P<language_id>\d+)$")
async def handle_language_change(
    update: Update, context: CallbackContext, language_id: int
) -> None:
    query = update.callback_query
    user = get_user(query.from_user.username)
    language = get_language(language_id)

    user.set_option("studied_language", language.id)
    response_message = f"Language changed to {language.name}."
    await send_message(update, context, response_message)
