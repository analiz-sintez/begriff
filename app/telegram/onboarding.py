import logging
from dataclasses import dataclass
from babel import Locale
from flag import flag

from app.srs.service import get_language
from core.bus import Signal
from core.auth import User
from core.messenger import Context
from core.i18n import TranslatableString as _
from core.messenger import Button, Keyboard

from .. import bus, router


logger = logging.getLogger(__name__)


# Part 0. Greet the user.
@dataclass
class OnboardingStarted(Signal):
    user_id: int


# Part 1. Select (default) native language.
# It is used as an interface language.
@dataclass
class DefaultNativeLanguageSelected(Signal):
    user_id: int
    native_language_id: int


@dataclass
class DefaultNativeLanguageEntered(Signal):
    user_id: int
    native_language_id: int


@dataclass
class DefaultNativeLanguageSaved(Signal):
    user_id: int
    native_language_id: int


# Part 2. Select study language.
@dataclass
class StudyLanguageAsked(Signal):
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
    language_code: str


@dataclass
class StudyLanguageSaved(Signal):
    """The bot saved study language chosen by the user."""

    user_id: int
    language_id: int


# Part 3. Test and add words.
@dataclass
class TestStarted(Signal):
    user_id: int
    native_language_id: int


@dataclass
class TestFinished(Signal):
    user_id: int
    native_language_id: int


# Part 4. Options
@dataclass
class RemindersSelected(Signal):
    user_id: int


# Part N. Finish onboarding.
@dataclass
class OnboardingFinished(Signal):
    user_id: int


def get_flag(ctx: Context, locale: Locale) -> str:
    if terr := ctx.config.LANGUAGE["territories"].get(locale.language):
        return flag(terr)
    return ""


@router.command("help", description="Describe commands")
@router.authorize()
async def help(ctx: Context, user: User) -> None:
    logger.info("User %s required help page.", user.id)
    await ctx.send_message(
        _(
            """
Welcome to the Begriff Bot! I'll help you learn new words in a foreign language.
        
Here are the commands you can use:
        
📝 Simply enter words separated by a newline to add them to your study list with automatic explanations.
🗣️ Write a sentence (30 chars or more) to check it for grammatical and lexical errors.
🌐 Paste a URL or share it from any app to get a recap in a language you study, with currently studied words.
📜 /list - See all the words you've added to your study list along with their details.
📚 /study - Start a study session with your queued words.
🌍 /language - Change your studied language.        
"""
        )
    )


@router.command("start", description="Start using the bot")
@router.authorize()
async def start(ctx: Context, user: User) -> None:
    """Launch the onboarding process."""
    await ctx.send_message(
        _(
            """
Welcome to the Begriff Bot! I'll help you learn new words in a foreign language.

In a few steps we'll set up things and start.      
""",
        )
    )
    bus.emit(OnboardingStarted(user.id), ctx=ctx)


@bus.on(OnboardingStarted)
@router.authorize()
async def ask_studied_language(ctx: Context, user: User):
    # Show a keyboard with available languages to study.
    # Or read the language name from the next message from the user.
    locales = [
        Locale.parse(code) for code in ctx.config.LANGUAGE["study_languages"]
    ]
    buttons = [
        Button(
            get_flag(ctx, locale)
            + locale.get_language_name(ctx.user.locale.language),
            StudyLanguageSelected(user.id, locale.language),
        )
        for locale in locales
    ]
    row_size = 4
    row_cnt = len(buttons) // row_size
    if len(buttons) % row_size > 0:
        row_cnt += 1
    keyboard = Keyboard(
        [buttons[row_size * i : row_size * (i + 1)] for i in range(row_cnt)]
    )
    await ctx.send_message(
        _("Select the language you want to study:"), keyboard
    )


@bus.on(StudyLanguageSelected)
@router.authorize()
async def save_studied_language(ctx: Context, user: User, language_code: str):
    locale = Locale.parse(language_code)
    language = get_language(locale.get_language_name("en"))
    await ctx.send_message(
        _(
            "You selected: {flag}{language}",
            flag=get_flag(ctx, locale),
            language=locale.get_language_name(ctx.user.locale.language),
        )
    )
    bus.emit(StudyLanguageSaved(user.id, language.id), ctx=ctx)


async def do_test(user: User):
    # Check if there's a word freq dict for the selected study language.
    # Randomly pick N words from the easiest 500 words.
    # Add them as word notes.
    # Get their front->back cards.
    # Show the cards to a user, each card only once.
    # Get the views and results.
    pass


@bus.on(OnboardingFinished)
@router.authorize()
async def finish_onboarding(ctx: Context, user: User):
    # Show a message with tips how to work with the bot.
    await ctx.send_message(_("Here we go"))
