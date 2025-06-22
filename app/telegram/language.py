import logging
from typing import Optional
import asyncio
from dataclasses import dataclass
from telegram import (
    Update,
    InlineKeyboardButton as Button,
    InlineKeyboardMarkup as Keyboard,
)
from telegram.ext import CallbackContext

from ..config import Config
from ..core import get_user, User
from ..srs import get_language, get_notes, Language
from ..ui import Signal, bus, encode
from .utils import send_message, authorize
from .router import router
from .note import get_explanation_in_native_language


logger = logging.getLogger(__name__)


@dataclass
class LanguageChangeRequested(Signal):
    user_id: int


@dataclass
class LanguageSelected(Signal):
    user_id: int
    language_id: int  # Studied language ID


@dataclass
class LanguageChanged(Signal):
    user_id: int
    language_id: int  # Studied language ID


@dataclass
class NativeLanguageAsked(Signal):
    user_id: int
    studied_language_id: int


@dataclass
class NativeLanguageSelected(Signal):
    user_id: int
    studied_language_id: int
    native_language_id: int


@dataclass
class NativeLanguageChanged(Signal):
    user_id: int
    studied_language_id: int
    native_language_id: int


@router.command(
    "language",
    args=["language_name", "native_language_name"],
    description="Change studied language or set its native language",
)
@authorize()
async def change_language(
    update: Update,
    context: CallbackContext,
    user: User,
    language_name: Optional[str] = None,
    native_language_name: Optional[str] = None,
) -> None:
    if language_name:
        # Setting a studied language.
        studied_language = get_language(language_name)
        if not studied_language:
            await send_message(
                update,
                context,
                f"Language '{language_name}' not found or could not be created.",
            )
            return

        user.set_option("studied_language", studied_language.id)
        response_message = (
            f"Studied language changed to {studied_language.name}."
        )
        bus.emit(
            LanguageChanged(user.id, studied_language.id),
            update=update,
            context=context,
        )

        if native_language_name:
            # Also setting native language for this studied language.
            native_language = get_language(native_language_name)
            if not native_language:
                await send_message(
                    update,
                    context,
                    f"Native language '{native_language_name}' not found or could not be created.",
                )
                return

            user.set_option(
                f"languages/{studied_language.id}/native_language",
                native_language.id,
            )
            response_message += (
                f"\n\nNative language for studying {studied_language.name} "
                f"set to {native_language.name}. "
                f"Explanations will be in {native_language.name}. "
            )
            if native_language.id == studied_language.id:
                response_message += f"This means explanations will be in {studied_language.name} itself."
            else:
                response_message += (
                    f"To retain explanations in {studied_language.name}, "
                    f"set it as native: /language {studied_language.name} {studied_language.name}."
                )
            bus.emit(
                NativeLanguageChanged(
                    user.id, studied_language.id, native_language.id
                )
            )
        else:
            # If only studied language is set, and no native language
            # is specified via command,we will ask for it interactively
            # via the LanguageChanged signal handler.
            pass

        await send_message(update, context, response_message)

    else:
        # Showing current language with language options to choose
        user_notes = get_notes(user_id=user.id)
        # Get unique language IDs from user's notes
        available_studied_lang_ids = {note.language_id for note in user_notes}
        # Ensure the currently set studied language (even if no notes exist for it) is an option,
        # and also the default study language from config.
        current_studied_lang_id = user.get_option("studied_language")
        if current_studied_lang_id:
            available_studied_lang_ids.add(current_studied_lang_id)

        default_study_lang_name = Config.LANGUAGE["defaults"]["study"]
        default_study_lang = get_language(default_study_lang_name)
        if default_study_lang:
            available_studied_lang_ids.add(default_study_lang.id)

        current_studied_lang = (
            get_language(current_studied_lang_id)
            if current_studied_lang_id
            else default_study_lang
        )

        response_message = (
            f"You are currently studying {current_studied_lang.name}."
            if current_studied_lang
            else "No studied language set. Defaulting to English."
        )

        if available_studied_lang_ids:
            response_message += "\n\nChoose a language you want to study:"
            buttons = []
            for lang_id in sorted(
                list(available_studied_lang_ids)
            ):  # Sort for consistent order
                lang = get_language(lang_id)
                if lang:
                    buttons.append(
                        Button(
                            lang.name,
                            callback_data=encode(
                                LanguageSelected(user.id, lang.id)
                            ),
                        )
                    )
            keyboard = Keyboard([buttons]) if buttons else None
        else:
            response_message += "\n\nYou don't have any notes yet. Add notes to create languages, or use `/language <name>`."
            keyboard = None

        await send_message(update, context, response_message, keyboard)


@bus.on(LanguageSelected)
@authorize()
async def handle_language_selected(
    update: Update, context: CallbackContext, user: User, language_id: int
) -> None:
    # This language_id is the new studied language
    studied_language = get_language(language_id)
    if not studied_language:
        await send_message(update, context, "Error selecting language.")
        return

    user.set_option("studied_language", studied_language.id)
    response_message = f"Studied language changed to {studied_language.name}."
    # We use await here to ensure the message about language change is sent before asking for native.
    await send_message(update, context, response_message)
    # Now emit LanguageChanged to trigger asking for native language
    bus.emit(
        LanguageChanged(user.id, studied_language.id),
        update=update,
        context=context,
    )


@bus.on(LanguageChanged)
@authorize()
async def ask_native_language(
    update: Update, context: CallbackContext, user: User, language_id: int
) -> None:
    # language_id here is the ID of the newly set *studied* language
    studied_language = get_language(language_id)
    if not studied_language:
        logger.error(
            f"Cannot find studied language with ID {language_id} for user {user.id}"
        )
        await send_message(
            update,
            context,
            "An error occurred while setting up native language options.",
        )
        return

    user_notes = get_notes(user_id=user.id)
    # Get unique language IDs from user's notes
    native_options_ids = {note.language_id for note in user_notes}

    # Add default native language from config
    default_native_lang_name = Config.LANGUAGE["defaults"]["native"]
    default_native_lang = get_language(default_native_lang_name)
    if default_native_lang:
        native_options_ids.add(default_native_lang.id)

    # Also add the studied language itself as an option for native
    native_options_ids.add(studied_language.id)

    if not native_options_ids:
        await send_message(
            update,
            context,
            f"No languages available to set as native for {studied_language.name}. "
            f"Explanations will be in {studied_language.name} by default.",
        )
        # Set studied language as its own native language by default if no other options.
        user.set_option(
            f"languages/{studied_language.id}/native_language",
            studied_language.id,
        )
        bus.emit(
            NativeLanguageChanged(
                user.id, studied_language.id, studied_language.id
            )
        )
        return

    buttons = []
    for lang_id_opt in sorted(
        list(native_options_ids)
    ):  # Sort for consistent order
        lang_opt = get_language(lang_id_opt)
        if lang_opt:
            buttons.append(
                Button(
                    lang_opt.name,
                    callback_data=encode(
                        NativeLanguageSelected(
                            user.id, studied_language.id, lang_opt.id
                        )
                    ),
                )
            )

    keyboard = Keyboard([buttons]) if buttons else None

    response_message = (
        f"Please select the native language for your {studied_language.name} studies. "
        "This will be the language of explanations."
    )
    bus.emit(
        NativeLanguageAsked(user.id, studied_language_id=studied_language.id)
    )
    await send_message(update, context, response_message, keyboard)


@bus.on(NativeLanguageSelected)
@authorize()
async def handle_native_language_selected(
    update: Update,
    context: CallbackContext,
    user: User,
    studied_language_id: int,
    native_language_id: int,
) -> None:
    studied_language = get_language(studied_language_id)
    native_language = get_language(native_language_id)

    if not studied_language or not native_language:
        logger.error(
            f"Error fetching languages: Studied ID {studied_language_id}, Native ID {native_language_id}"
        )
        await send_message(
            update,
            context,
            "An error occurred while setting the native language.",
        )
        return

    user.set_option(
        f"languages/{studied_language.id}/native_language",
        native_language.id,
    )

    response_message = (
        f"Native language for {studied_language.name} set to {native_language.name}. "
        f"Explanations will now be in {native_language.name}."
    )
    if studied_language.id == native_language.id:
        response_message = (
            f"Native language for {studied_language.name} set to itself. "
            f"Explanations will be in {studied_language.name}."
        )

    bus.emit(
        NativeLanguageChanged(user.id, studied_language.id, native_language.id)
    )
    await send_message(update, context, response_message)


def _handle_translation_task_error(task: asyncio.Task) -> None:
    """Callback to log exceptions from background translation tasks."""
    try:
        task.result()  # This will re-raise the exception if one occurred
    except asyncio.CancelledError:
        logger.warning("Note translation task was cancelled.")
    except Exception as e:
        logger.error(
            f"Error in background note translation task: {e}", exc_info=True
        )


@bus.on(NativeLanguageChanged)
async def generate_note_translations(
    user_id: int, studied_language_id: int, native_language_id: int
):
    if studied_language_id == native_language_id:
        return
    # Prepare translations of explanations for all the cards
    # of the studied language. These will run concurrently in the background.
    logger.info(
        f"Starting background translation tasks for user {user_id}, language {studied_language_id}"
    )
    for note in get_notes(user_id=user_id, language_id=studied_language_id):
        task = asyncio.create_task(get_explanation_in_native_language(note))
        task.add_done_callback(_handle_translation_task_error)
        # Sleep to potentially rate-limit the initiation of API calls
        # or database operations within get_explanation_in_native_language.
        # await asyncio.sleep(0.1)
    logger.info(
        f"Finished creating background translation tasks for user {user_id}, language {studied_language_id}"
    )
