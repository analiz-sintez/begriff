import logging
import asyncio
from dataclasses import dataclass
from typing import List

from babel import Locale

from nachricht.auth import User
from nachricht.bus import Signal, TerminalSignal
from nachricht.messenger import Context, Keyboard, Button
from nachricht.i18n import TranslatableString as _

from .. import bus, router
from ..notes import (
    language_code_by_name,
    Language,
    get_studied_language,
    get_native_language,
)
from ..srs import get_notes


logger = logging.getLogger(__name__)


def _pack_buttons(buttons: List[Button], row_size: int) -> List[List[Button]]:
    """
    Pack buttons into button rows, with `row_size` items in a row.
    """
    assert row_size > 0
    row_cnt = len(buttons) // row_size
    if len(buttons) % row_size > 0:
        row_cnt += 1
    return [buttons[row_size * i : row_size * (i + 1)] for i in range(row_cnt)]


################################################################
# Native language selection

# Select (default) native language.
# It is used as an interface language.


@dataclass
class NativeLanguageConfirmed(Signal):
    """User confirmed the default native language."""

    user_id: int
    language_code: str


@dataclass
class NativeLanguageAsked(Signal):
    """Bot asks a user to select a language to study."""

    user_id: int


@dataclass
class NativeLanguageChangeRequested(Signal):
    """User requested a menu to pick up the native language."""

    user_id: int


@dataclass
class NativeLanguageSelected(Signal):
    """A user selected study language from the list."""

    user_id: int
    language_code: str


@dataclass
class NativeLanguageSaved(Signal):
    """The bot saved study language chosen by the user."""

    user_id: int
    language_id: int


@router.authorize()
async def ask_for_native_language(ctx: Context, user: User):
    language = Language.from_locale(ctx.locale)
    keyboard = Keyboard(
        [
            [
                # this button is purposefully not translated:
                # a user should always be able to switch to understandable language
                Button(
                    "Switch to English", NativeLanguageSelected(user.id, "en")
                ),
                Button(
                    _("Select other language"),
                    NativeLanguageChangeRequested(user.id),
                ),
            ],
            [
                Button(
                    _("Continue"),
                    NativeLanguageConfirmed(user.id, language.code),
                )
            ],
        ]
    )

    await ctx.send_message(
        _(
            "Your current interface language is {language_name}{flag}. You can change it or proceed.",
            language_name=language.get_localized_name(ctx.locale),
            flag=language.flag,
        ),
        keyboard,
    )
    bus.emit(NativeLanguageAsked(user.id), ctx=ctx)


@bus.on(NativeLanguageChangeRequested)
@router.authorize()
async def ask_native_language_selection(ctx: Context, user: User):
    codes = ctx.config.LANGUAGE["study_languages"]
    languages = [Language.from_code(code) for code in codes]
    buttons = [
        Button(
            text=language.flag + language.get_localized_name(ctx.locale),
            callback=NativeLanguageSelected(user.id, language.code),
        )
        for language in languages
    ]
    keyboard = Keyboard(_pack_buttons(buttons, row_size=4))
    return await ctx.send_message(
        _("Select your interface language:"), keyboard
    )


@bus.on(NativeLanguageSelected)
@bus.on(NativeLanguageConfirmed)
@router.authorize()
async def save_native_language(ctx: Context, user: User, language_code: str):
    user.set_option("locale", language_code)
    language = Language.from_code(language_code)
    user.set_option("native_language", language.id)

    await ctx.send_message(
        _(
            "Interface language set to {language}{flag}.",
            language=language.get_localized_name(ctx.locale),
            flag=language.flag,
        )
    )

    bus.emit(NativeLanguageSaved(user.id, language.id), ctx=ctx)


################################################################
# Study language selection


@dataclass
class StudyLanguageChangeStarted(Signal):
    """A user asks the bot to change the language they study."""

    user_id: int


@dataclass
class StudyLanguageAsked(Signal):
    """Bot asks a user to select a language to study."""

    user_id: int


@dataclass
class StudyLanguageSelected(Signal):
    """A user selected study language from the list."""

    user_id: int
    language_code: str


@dataclass
class StudyLanguageEntered(TerminalSignal):
    """A user manually entered study language name."""

    user_id: int


@dataclass
class StudyLanguageSaved(Signal):
    """The bot saved study language chosen by the user."""

    user_id: int
    language_id: int


@router.command("language", description=_("Change studied language"))
@router.authorize()
async def start_change_studied_language_scenario(ctx: Context, user: User):
    # This function is needed to unbind the language change menu
    # from the command. It allows to reuse the function e.g. in
    # the onboarding process.

    # ctx.start_conversation(scenario="change_studied_language")
    bus.emit(StudyLanguageChangeStarted(user.id), ctx=ctx)


@bus.on(StudyLanguageChangeStarted)
@router.authorize()
async def ask_studied_language(ctx: Context, user: User):
    # Show a keyboard with available languages to study.
    # Or read the language name from the next message from the user.
    codes = ctx.config.LANGUAGE["study_languages"]
    languages = [Language.from_code(code) for code in codes]
    buttons = [
        Button(
            text=language.flag + language.get_localized_name(ctx.locale),
            callback=StudyLanguageSelected(user.id, language.code),
        )
        for language in languages
    ]
    keyboard = Keyboard(_pack_buttons(buttons, row_size=4))
    return await ctx.send_message(
        _("Select the language you want to study:"),
        keyboard,
        on_reply=StudyLanguageEntered(user_id=user.id),
        new=True,
    )


@bus.on(StudyLanguageEntered)
@router.authorize()
async def parse_studied_language(ctx, user):
    try:
        input = ctx.message.text.strip().lower()
        if len(input) == 2:
            locale = Locale(input)
        else:
            code = language_code_by_name(input)
            locale = Locale.parse(code)
        bus.emit(StudyLanguageSelected(user.id, locale.language), ctx=ctx)
    except Exception as e:
        logger.error("Exception while parsing studied language name: %s", e)
        await ctx.send_message(_("Couldn't parse the language you entered."))


@bus.on(StudyLanguageSelected)
@router.authorize()
async def save_studied_language(ctx: Context, user: User, language_code: str):
    language = Language.from_code(language_code)
    user.set_option("studied_language", language.id)
    await ctx.send_message(
        _(
            "You now study {flag}{language}.",
            flag=language.flag,
            language=language.get_localized_name(ctx.locale),
        )
    )
    bus.emit(StudyLanguageSaved(user.id, language.id), ctx=ctx)
    # ctx.emit(StudyLanguageSaved(user.id, language.id))


################################################################
# Utility functions


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


@bus.on(NativeLanguageSaved)
@bus.on(StudyLanguageSaved)
@router.authorize()
async def generate_note_translations(
    ctx: Context, user: User, language_id: int
):
    studied_language = get_studied_language(user)
    native_language = get_native_language(user)
    if studied_language.id == native_language.id:
        return
    # Prepare translations of explanations for all the cards
    # of the studied language. These will run concurrently in the background.
    logger.info(
        f"Starting background translation tasks for user {user.login}, language {studied_language.name}"
    )
    for note in get_notes(user_id=user.id, language_id=studied_language.id):
        task = asyncio.create_task(note.get_display_text())
        task.add_done_callback(_handle_translation_task_error)
    logger.info(
        f"Finished creating background translation tasks for user {user.login}, language {studied_language.name}"
    )
