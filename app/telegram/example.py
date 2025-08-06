import logging
import re

from dataclasses import dataclass

from nachricht.bus import Signal
from nachricht.auth import User
from nachricht.messenger import Context, Emoji
from nachricht.i18n import TranslatableString as _
from nachricht.db import db

from .. import bus, router
from .language import Language
from .note import (
    Note, Context,
    get_native_language,
    get_studied_language,
    query_llm,
    get_note,
    format_explanation,
)
from ..notes import (
    ExampleNote
)


logger = logging.getLogger(__name__)


@dataclass
class ExampleRequested(Signal):
    """User requested usage examples for a note."""

    note_id: int


@dataclass
class ExamplesSent(Signal):
    """Usage examples for a note sent to the user."""

    note_id: int


@dataclass
class ExampleDownvoted(Signal):
    """The user downvoted usage example we sent to them."""

    note_id: int


async def get_usage_example(note: Note, ctx: Context):
    language = Language.from_id(note.language_id)
    native_language = get_native_language(note.user)
    return await query_llm(
        f"""
You are {language.name} tutor helping a student to learn new language. Their native language is {native_language.name}.

Generate a single usage example for the given word or phrase.

- This example should be a full sentence.
- If a word has multiple different meanings, provide an example showing most common meaning. Indicate this meaning in square brackets in student's native language.

The pattern: the student studies German and their native language is English, the word is: "Konto".

Your response:

"[Bank account] Ich habe ein neues Konto bei der Bank eröffnet, um mein Geld sicher zu verwalten."
        """,
        note.field1,
    )


@bus.on(ExampleRequested)
@bus.on(ExampleDownvoted)
@router.authorize()
async def give_usage_example(ctx: Context, user: User, note_id: int) -> None:
    if not (note := get_note(note_id)):
        return

    try:
        example = await get_usage_example(note, ctx)
        response = format_explanation(example)

        message = await ctx.send_message(
            text=response,
            reply_to=ctx.message,
            on_reaction={
                Emoji.THUMBSDOWN: ExampleDownvoted(note.id),
                Emoji.THUMBSUP: ExampleUpvoted(note.id)
            },
        )
        ctx.context(message)["example"] = example
        bus.emit(ExamplesSent(note.id))

    except Exception as e:
        logging.error(f"Got error while making an example: {e}")
        response = _("Couldn't make an example, sorry.")

        message = await ctx.send_message(
            text=response,
            reply_to=ctx.message,
        )

    return message


@dataclass
class ExampleUpvoted(Signal):
    note_id: int
    # text: str


@dataclass
class ExampleNoteAdded(Signal):
    note_id: int


@bus.on(ExampleUpvoted)
@router.authorize()
async def add_example_to_deck(ctx: Context, user: User, note_id: int) -> None:
    if not (note := get_note(note_id)):
        return

    # Get the example text from the message that was upvoted
    example_text = ctx.context(ctx.bot_message)["example"]

    # Create an example note
    studied_language = get_studied_language(user)

    # Create the example note with reference to original note
    example_note = ExampleNote(
        field1=example_text,
        field2=None,
        user_id=user.id,
        language_id=studied_language.id,
    )

    # Store the link to the original note
    example_note.set_option("linked_note_id", note_id)

    # db.session.add(example_note)
    # db.session.flush()

    # # Create cards for the example note
    # from datetime import datetime, timezone
    # from ..srs import DirectCard, ReverseCard, CardAdded

    # now = datetime.now(timezone.utc)
    # front_card = DirectCard(note_id=example_note.id, ts_scheduled=now)
    # back_card = ReverseCard(note_id=example_note.id, ts_scheduled=now)

    # db.session.add_all([front_card, back_card])
    # db.session.commit()

    # bus.emit(CardAdded(front_card.id))
    # bus.emit(CardAdded(back_card.id))
    #
    bus.emit(ExampleNoteAdded(example_note.id))

    await ctx.send_message(
        text=f"✅ Example added to your deck: *{example_text}*",
        reply_to=ctx.message,
        new=False,
    )
