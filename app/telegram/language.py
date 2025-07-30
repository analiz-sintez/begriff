import logging
import asyncio
from dataclasses import dataclass
from typing import List

from flag import flag
from babel import Locale

from core.auth import User
from core.bus import Signal
from core.messenger import Context, Keyboard, Button
from core.i18n import TranslatableString as _

from .. import bus, router
from ..notes import get_language, language_code_by_name
from ..srs import get_notes
from .note import get_explanation_in_native_language

# from .onboarding import


logger = logging.getLogger(__name__)


def get_flag(ctx: Context, locale: Locale) -> str:
    if terr := ctx.config.LANGUAGE["territories"].get(locale.language):
        return flag(terr)
    return ""


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
    current_locale = ctx.locale
    language_code = current_locale.language
    language_name = current_locale.get_language_name(language_code)

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
                    NativeLanguageConfirmed(user.id, language_code),
                )
            ],
        ]
    )

    await ctx.send_message(
        _(
            "Your current interface language is {language_name}{flag}. You can change it or proceed.",
            language_name=language_name,
            flag=get_flag(ctx, current_locale),
        ),
        keyboard,
    )
    bus.emit(NativeLanguageAsked(user.id), ctx=ctx)


@bus.on(NativeLanguageChangeRequested)
@router.authorize()
async def ask_native_language_selection(ctx: Context, user: User):
    locales = [
        Locale.parse(code) for code in ctx.config.LANGUAGE["study_languages"]
    ]
    buttons = [
        Button(
            text=get_flag(ctx, locale)
            + locale.get_language_name(ctx.locale.language),
            callback=NativeLanguageSelected(user.id, locale.language),
        )
        for locale in locales
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
    locale = Locale.parse(language_code)
    language = get_language(locale.get_language_name("en"))
    user.set_option("native_language", language.id)

    await ctx.send_message(
        _(
            "Interface language set to {language}{flag}.",
            language=locale.get_language_name(ctx.locale.language),
            flag=get_flag(ctx, locale),
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
class StudyLanguageEntered(Signal):
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
    locales = [
        Locale.parse(code) for code in ctx.config.LANGUAGE["study_languages"]
    ]
    buttons = [
        Button(
            text=get_flag(ctx, locale)
            + locale.get_language_name(ctx.locale.language),
            callback=StudyLanguageSelected(user.id, locale.language),
        )
        for locale in locales
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
    locale = Locale.parse(language_code)
    language = get_language(locale.get_language_name("en"))
    user.set_option("studied_language", language.id)
    await ctx.send_message(
        _(
            "You now study {flag}{language}.",
            flag=get_flag(ctx, locale),
            language=locale.get_language_name(ctx.locale.language),
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
    studied_language = get_language(user.get_option("studied_language"))
    native_language = get_language(user.get_option("native_language"))
    if studied_language.id == native_language.id:
        return
    # Prepare translations of explanations for all the cards
    # of the studied language. These will run concurrently in the background.
    logger.info(
        f"Starting background translation tasks for user {user.login}, language {studied_language.name}"
    )
    for note in get_notes(user_id=user.id, language_id=studied_language.id):
        task = asyncio.create_task(
            get_explanation_in_native_language(ctx, note)
        )
        task.add_done_callback(_handle_translation_task_error)
    logger.info(
        f"Finished creating background translation tasks for user {user.login}, language {studied_language.name}"
    )
