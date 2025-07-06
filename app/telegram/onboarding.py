import logging
from dataclasses import dataclass

from core.bus import Signal, bus, encode
from core.auth import User
from core.messenger import router, Context, authorize


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
class StudyLanguageSelected(Signal):
    user_id: int
    study_language_id: int


@dataclass
class StudyLanguageEntered(Signal):
    user_id: int
    study_language_id: int


@dataclass
class StudyLanguageSaved(Signal):
    user_id: int
    native_language_id: int


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


@router.command("help", description="Describe commands")
@authorize()
async def help(ctx: Context, user: User) -> None:
    logger.info("User %s required help page.", user.id)
    await ctx.send_message(
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


@router.command("start", description="Start using the bot")
@authorize()
async def start(ctx: Context, user: User) -> None:
    """Launch the onboarding process."""
    await ctx.send_message(
        """
Welcome to the Begriff Bot! I'll help you learn new words in a foreign language.

In a few steps we'll set up things and start.      
""",
    )
    bus.emit(OnboardingStarted(user.id), ctx=ctx)


@bus.on(OnboardingStarted)
@authorize()
async def select_native_language(ctx: Context, user: User):
    # Show a keyboard with available languages to study.
    # Or read the language name from the next message from the user.
    bus.emit(OnboardingFinished(user.id), ctx=ctx)


async def handle_native_language():
    pass


async def select_study_language():
    pass


async def handle_study_language():
    pass


async def do_test(user: User):
    # Check if there's a word freq dict for the selected study language.
    # Randomly pick N words from the easiest 500 words.
    # Add them as word notes.
    # Get their front->back cards.
    # Show the cards to a user, each card only once.
    # Get the views and results.
    pass


@bus.on(OnboardingFinished)
@authorize()
async def finish_onboarding(ctx: Context, user: User):
    # Show a message with tips how to work with the bot.
    await ctx.send_message("Here we go")
