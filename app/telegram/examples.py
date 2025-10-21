import logging
import re
from dataclasses import dataclass

from nachricht.auth import User
from nachricht.messenger import Context, Emoji
from nachricht.bus import Signal
from nachricht.i18n import TranslatableString as _
from nachricht.db import db

from .. import router, bus
from ..notes import get_note, Language, get_native_language
from ..srs import format_explanation
from ..llm import get_usage_examples
from ..notes.example_note import ExampleNote, ExampleLink


logger = logging.getLogger(__name__)


@dataclass
class ExamplesRequested(Signal):
    """User requested usage examples for a note."""

    note_id: int


@dataclass
class ExamplesSent(Signal):
    """Usage examples for a note sent to the user."""

    note_id: int


@dataclass
class ExamplesDownvoted(Signal):
    """The user downvoted usage examples we sent to them."""

    note_id: int


@bus.on(ExamplesRequested)
@router.authorize()
async def give_usage_examples(ctx: Context, user: User, note_id: int) -> None:
    if not (note := get_note(note_id)):
        return

    # 1. check if a note already has ExampleNotes linked to it
    example_links = ExampleLink.query.filter_by(from_id=note.id).all()
    example_notes = [
        ExampleNote.query.filter_by(id=link.to_id).first()
        for link in example_links
    ]
    examples = [note.field1 for note in example_notes if note]

    if len(examples) < 3:
        # 2. if they're missing, create three examples
        try:
            native_language = get_native_language(user)
            for _ in range(3 - len(examples)):
                example_text = await get_usage_examples(
                    note, native_language, examples
                )
                # parse example and create ExampleNote
                match = re.match(
                    r"\[(?P<topic>.*)\] (?P<text>.*)", example_text
                )
                if match:
                    topic = match.group("topic")
                    text = match.group("text")
                else:
                    topic = None
                    text = example_text
                example_note = ExampleNote(
                    field1=text,
                    user_id=user.id,
                    language_id=note.language_id,
                )
                if topic:
                    example_note.set_topic(topic)
                db.session.add(example_note)
                db.session.flush()
                example_link = ExampleLink(
                    from_id=note.id,
                    to_id=example_note.id,
                    user_id=user.id,
                )
                db.session.add(example_link)
                db.session.commit()
                examples.append(example_text)
        except Exception as e:
            logging.error(f"Got error while making examples: {e}")
            response = _("Couldn't make examples, sorry.")
            await ctx.send_message(
                text=response,
                reply_to=ctx.message,
            )
            return

    # 3. then send three examples as three separate messages
    for example in examples:
        response = format_explanation(example)
        await ctx.send_message(
            text=response,
            reply_to=ctx.message,
            on_reaction={Emoji.THUMBSDOWN: ExamplesDownvoted(note.id)},
        )
    bus.emit(ExamplesSent(note.id))


@bus.on(ExamplesDownvoted)
@router.authorize()
async def downvote_example(ctx: Context, user: User, note_id: int):
    # 1. get the message text
    message_text = ctx.message.text
    # 2. find the example note
    example_note = ExampleNote.query.filter_by(field1=message_text).first()
    if not example_note:
        return
    # 3. delete the example note and link
    example_link = ExampleLink.query.filter_by(to_id=example_note.id).first()
    if example_link:
        db.session.delete(example_link)
    db.session.delete(example_note)
    db.session.commit()
    # 4. regenerate the example
    bus.emit(ExamplesRequested(note_id))
