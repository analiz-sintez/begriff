import logging
import asyncio
from dataclasses import dataclass

from nachricht.bus import Signal
from nachricht.auth import User
from nachricht.messenger import Context, Emoji
from nachricht.i18n import TranslatableString as _, resolve

from .. import bus, router, Config
from ..notes import get_native_language, get_studied_language
from .note import UserInputProcessed
from .study import StudySessionRequested, StudySessionFinished, CardGraded

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
class NotesAddedDuringOnboarding(Signal):
    user_id: int


@bus.on(StudyLanguageSaved, {"action": "onboarding"})
@router.authorize()
async def show_how_to_add_notes(ctx: Context):
    text = """In a hole in the ground there lived a hobbit. Not a nasty, dirty, wet hole, filled with the ends of worms and an oozy smell, nor yet a dry, bare, sandy hole with nothing in it to sit down on or to eat: it was a hobbit-hole, and that means comfort."""
    studied_language = get_studied_language(ctx.user)
    text_in_studied_language = await resolve(_(text), studied_language.locale)
    image_path = await generate_image(text, studied_language)
    return await ctx.send_message(
        _(
            """
Now that you've selected a language to study, we can begin.

Imagine you're reading a book. Here's a paragraph:

> {text}

Pick one or two words you don't understand, write each on a new line, and send them to me. Watch what happens.
""",
            text=text_in_studied_language,
        ),
        new=True,
        image=image_path,
        on_reply=NotesAddedDuringOnboarding(ctx.user.id),
    )


@bus.on(UserInputProcessed, {"action": "onboarding"})
@router.authorize()
async def tell_how_to_study_cards(ctx: Context):
    text = """Then Bilbo sat down on a seat by his door, crossed his legs, and blew out a beautiful grey ring of smoke that sailed up into the air without breaking and floated away over The Hill. (Hobbits don't wear shoes!)"""
    studied_language = get_studied_language(ctx.user)
    image_path = await generate_image(text, studied_language)

    message = await ctx.send_message(
        _(
            """
So now you know what those words mean — and hopefully you understand the paragraph better. But will you still remember them in a week or two, or when you see them again in another text?

To strengthen your memory, spend a few minutes each day reviewing the words you’ve looked up. Here's how it works:

☝️ I’ll show you a word, and you try to recall its meaning.

✌️ If you remember it, press "ANSWER" to check. Then rate your recall — I’ll schedule your next review accordingly.

🖐 If you can’t recall it, press "ANSWER" anyway, read the explanation, and try to memorize it again.

There’s solid science behind how this works — the better you remember a word, the less often you’ll see it. But if you're starting to forget it, I’ll make sure it comes up again.
"""
        ),
        new=True,
        image=image_path,
    )
    await asyncio.sleep(2)
    bus.emit(StudySessionRequested(ctx.user.id), ctx=ctx)


@bus.on(CardGraded, {"action": "onboarding"})
# @bus.on(StudySessionFinished, {"action": "onboarding"})
@router.authorize()
async def tell_about_other_commands(ctx: Context):
    del ctx.context(ctx.conversation)["action"]
    native_language = get_native_language(ctx.user)
    studied_language = get_studied_language(ctx.user)
    message = await ctx.send_message(
        _(
            """
You can start a study session anytime with the /study command. Practice regularly, and progress will follow in no time.

Other useful commands to try:

• `!!` — translates a phrase from {native_flag} to {studied_flag}.

• `??` — clarifies tricky parts in {studied_flag}.

• Send me a text longer than 30 characters — I’ll check it for mistakes.

• Send me the URL of an article — I’ll summarize it for you, highlighting words you’re learning (try it on Wikipedia!).

• Didn’t like my explanation? React with 👎 and I’ll redo it.

• Need a usage example? React with 🙏 and I’ll give you one.

You can open the cheatsheet anytime with the /help command.
            
Good luck!
""",
            native_flag=native_language.flag,
            studied_flag=studied_language.flag,
            Emoji=Emoji,
        ),
        new=True,
        # image=image_path,
    )
    bus.emit(OnboardingFinished(ctx.user.id), ctx=ctx)
    return message


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
