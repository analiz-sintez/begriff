import logging
import asyncio
from dataclasses import dataclass
from typing import List

from nachricht.bus import Signal
from nachricht.auth import User
from nachricht.messenger import Context
from nachricht.i18n import TranslatableString as _, resolve
from nachricht.messenger import Button, Keyboard

from .. import bus, router, Config
from ..llm import translate
from ..util import get_studied_language
from .note import ExplanationNoteShown
from .study import StudySessionRequested, StudySessionFinished

if Config.IMAGE["enable"]:
    from ..image import generate_image
else:

    async def generate_image(*args, **kwargs):
        return None


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
# Adding notes


@dataclass
class NotesAddedFirstTime(Signal):
    user_id: int


@bus.on(StudyLanguageSaved, {"action": "onboarding"})
@router.authorize()
async def show_how_to_add_notes(ctx: Context):
    # ctx.context(ctx.conversation)["stage"] = "add_notes"
    text = """In a hole in the ground there lived a hobbit. Not a nasty, dirty, wet hole, filled with the ends of worms and an oozy smell, nor yet a dry, bare, sandy hole with nothing in it to sit down on or to eat: it was a hobbit-hole, and that means comfort."""
    studied_language = get_studied_language(ctx.user)
    text_in_studied_language = await resolve(_(text), studied_language.locale)
    image_path = await generate_image(text)
    return await ctx.send_message(
        _(
            """
Now that we've selected the language to study, we can start.

Let's assume you're reading a book. Here's a paragraph:

> {text}

Pick a word or two which you don't understand, write them down (each on a new line), and send them to me. See what happens.
""",
            text=text_in_studied_language,
        ),
        new=True,
        image=image_path,
        on_reply=NotesAddedFirstTime(ctx.user.id),
    )


# @bus.on(ExplanationNoteShown, {"stage": "add_notes"})
@bus.on(NotesAddedFirstTime, {"action": "onboarding"})
@router.authorize()
async def tell_how_to_study_cards(ctx: Context):
    # ctx.context(ctx.conversation)["stage"] = "study_cards"

    text = """Then Bilbo sat down on a seat by his door, crossed his legs, and blew out a beautiful grey ring of smoke that sailed up into the air without breaking and floated away over The Hill."""
    image_path = await generate_image(text)
    # wait while notes are sent
    # await asyncio.sleep(7)

    message = await ctx.send_message(
        _(
            """
So now you know what those words mean, and hopefully you understand the paragraph. But would you remember them in a week or two, or when you encounter them again in a new text?

To make your memorization firm, devote several minutes a day to rehearse the words you searched. See how it works:

- I show you a word, and you try to recall its meaning.
- If you succeed, you press "ANSWER" and check if you recalled correctly. Grade your memory, and I'll plan the next rehearsal accordingly.
- If you couldn't recall it, press "ANSWER" anyway, read the meaning and try to remember it.

There's the whole science behind how you rate your memorization and how often I show you the cards. You don't spend time on things you're remembered good, and don't miss the words you're almost forgot.
"""
        ),
        new=True,
        image=image_path,
    )
    bus.emit(StudySessionRequested(ctx.user.id), ctx=ctx)


@bus.on(StudySessionFinished, {"action": "onboarding"})
async def tell_about_other_commands(ctx: Context):
    return await ctx.send_message(
        _(
            """
You can call a study session any time you want with `/study`.  Study regularly, and your progress will come in no time.

Other useful commands to explore:
- `!!` translates a phrase from {native_flag} to {study_flag}
- `??` clarifies tricky places in {study_flag}
- send me a long enough text (>30 characters) and I'll check it for errors
- send me an URL of an article and I'll make a recap for you, with the words you're currently studying (try wikipedia)
- if you don't like the explanation I did for you, react with a finger down emoji and I'll redo it.
- send me a long enough text (>30 characters) and I'll check it for errors
- if you need a usage example, send :pray: emoji

You can the cheatsheet page any time with `/help` command.

Good luck!
"""
        ),
        new=True,
        # image=image_path,
        # on_reply=NotesAddedFirstTime(ctx.user.id),
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
@router.authorize()
async def finish_onboarding(ctx: Context, user: User):
    # Show a message with tips how to work with the bot.
    await ctx.send_message(_("Here we go"), new=True)
