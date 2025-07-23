import logging
from dataclasses import dataclass
from typing import List
from babel import Locale
from flag import flag

from app.srs.service import get_language
from core.bus import Signal
from core.auth import User
from core.messenger import Context
from core.i18n import TranslatableString as _
from core.messenger import Button, Keyboard

from .. import bus, router
from ..srs import language_code_by_name


logger = logging.getLogger(__name__)


################################################################
# Part 0. Greet the user.
@dataclass
class OnboardingStarted(Signal):
    user_id: int


################################################################
# Part 3. Test and add words.
@dataclass
class TestStarted(Signal):
    user_id: int
    native_language_id: int


@dataclass
class TestFinished(Signal):
    user_id: int
    native_language_id: int


################################################################
# Part 4. Options
@dataclass
class RemindersSelected(Signal):
    user_id: int


################################################################
# Part N. Finish onboarding.
@dataclass
class OnboardingFinished(Signal):
    user_id: int


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


@router.command("help", description="Describe commands")
@router.authorize()
async def show_help_message(ctx: Context, user: User) -> None:
    logger.info("User %s required help page.", user.id)
    await ctx.send_message(
        _(
            """
Welcome to Begriff Bot!
I’m here to help you learn and explore new words in a foreign language.

Here’s what you can do:

📝 Add words to your study list — Just send a list of words (one per line), and I’ll explain them automatically.
🗣️ Check a sentence — Send a sentence (30+ characters) to get feedback on grammar and word choice.
🔤 Translate or clarify —
    Start your message with !! to translate from your native language to the one you're studying.
    Use ?? to ask for clarification on something confusing.

💬 React to my replies:
    🤔 for help with your options
    🙏 to get more details or examples
    👎 if you didn’t like the answer — I’ll try again

🌐 Share a URL — Paste a link to get a summary in your target language, using words you’ve been learning.

📜 /list — View your saved words and their details
📚 /study — Begin a study session with your words
🌍 /language — Change the language you're learning
🚀 /start — Launch the tutorial and setup
❓ /help — See this command guide anytime
"""
        )
    )


@router.command("start", description="Start using the bot")
@router.authorize()
async def start_onboarding(ctx: Context, user: User) -> None:
    """Launch the onboarding process."""
    await ctx.send_message(
        _(
            """
Welcome to the Begriff Bot! I'll help you learn new words in a foreign language.

In a few steps we'll set up things and start.      
""",
        )
    )
    # how to make chains of signals reusable:
    # - here we set some mark: "this is onboarding"
    # - all the chains of signals starting from the signal with this mark
    # should carry it
    # - bus.on can check if there's a mark and decide if the chain should go
    # I.e. @bus.on(NativeLanguageSaved, conditions={'onboarding': True})
    # launches a slot only if there is onboarding mark ON THE SIGNAL.
    # This is not a global flag, hence it doesn't introduce side effects.
    # How will this work?
    # - Context object should carry `signal` property, which stores the current
    # signal if the request started from it
    #   - what if there are several signals? Should they be added to the list?
    #   - what if it's a study session? The signals list will be endless
    #   - signals are lightweight, even a thousand of them is not that much,
    #     but still it poses a vulnerability
    # - Bus dispatcher code looks at the signal and checks conditions
    #   - at which signal should it look?
    # Interface can be modelled well with a directed graph.
    # - Signals are arrows, but not exactly arrows
    # - Should we store all the path along the graph?
    # - Should we have a state for each walk along the graph? Not global.
    # Where such walk starts?
    # - from any non-signal event: command, callback, message
    # - maybe the walk should have a timeout
    # - if another walk starts, should the previous one end? not necessarily
    # - now messaes and their context is used to track walks
    bus.emit(OnboardingStarted(user.id), ctx=ctx)


################################################################
# Native language selection

# Select (default) native language.
# It is used as an interface language.


# @dataclass
# class NativeLanguageSaved(Signal):
#     user_id: int
#     language_code: str


@dataclass
class NativeLanguageConfirmed(Signal):
    """User confirmed the default native language."""

    user_id: int


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


@bus.on(OnboardingStarted)
@router.authorize()
async def ask_for_native_language(ctx: Context, user: User):
    current_locale = ctx.locale
    language_name = current_locale.get_language_name(current_locale.language)

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
            [Button(_("Continue"), NativeLanguageConfirmed(user.id))],
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
@bus.on(NativeLanguageSaved)
@bus.on(NativeLanguageConfirmed)
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
