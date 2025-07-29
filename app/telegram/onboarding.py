import logging
from dataclasses import dataclass
from typing import List

from core.bus import Signal
from core.auth import User
from core.messenger import Context
from core.i18n import TranslatableString as _
from core.messenger import Button, Keyboard

from .. import bus, router


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
📚 /check — Another way to check a sentence for grammar
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
    ctx.start_conversation(action="onboarding")
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


from .language import (
    NativeLanguageSaved,
    ask_for_native_language,
    ask_studied_language,
    StudyLanguageSaved,
)

bus.connect(
    OnboardingStarted, ask_for_native_language, {"action": "onboarding"}
)
bus.connect(
    NativeLanguageSaved, ask_studied_language, {"action": "onboarding"}
)


################################################################
# Other parts


async def do_test(user: User):
    # Check if there's a word freq dict for the selected study language.
    # Randomly pick N words from the easiest 500 words.
    # Add them as word notes.
    # Get their front->back cards.
    # Show the cards to a user, each card only once.
    # Get the views and results.
    pass


@bus.on(OnboardingFinished)
@bus.on(StudyLanguageSaved, {"action": "onboarding"})
# @router.on(OnboardingFinished)
# @router.on(StudyLanguageSaved, {"action": "onboarding"})
@router.authorize()
async def finish_onboarding(ctx: Context, user: User):
    # Show a message with tips how to work with the bot.
    await ctx.send_message(_("Here we go"), new=True)
