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
from ..llm import get_usage_example
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
class ExampleDownvoted(Signal):
    """The user downvoted usage examples we sent to them."""

    example_note_id: int


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

    for example_num in range(3):
        if example_num >= len(example_notes):
            example_dict = await get_usage_example(
                note,
                [
                    await note.get_display_text(translate=False)
                    for note in example_notes
                    if note
                ],
            )

            example_note = ExampleNote(
                field1=example_dict["text"],
                field2=example_dict["topic"],  # topic is in studied language
                user_id=user.id,
                language_id=note.language_id,
            )
            db.session.add(example_note)
            db.session.flush()
            example_link = ExampleLink(
                from_id=note.id,
                to_id=example_note.id,
                user_id=user.id,
            )
            db.session.add(example_link)
            db.session.commit()
            example_notes.append(example_note)

        example_note = example_notes[example_num]
        await ctx.send_message(
            text=format_explanation(await example_note.get_display_text()),
            reply_to=ctx.message,
            new=True,
            on_reaction={Emoji.THUMBSDOWN: ExampleDownvoted(example_note.id)},
        )

    bus.emit(ExamplesSent(note.id))


@bus.on(ExampleDownvoted)
@router.authorize()
async def redo_example(ctx: Context, user: User, example_note_id: int):
    """
    Regenerate an example, editing it inplace.
    """
    example_note = get_note(example_note_id)
    if not example_note:
        return
    link = ExampleLink.query.filter_by(to_id=example_note.id).first()
    word_note = link.note_from

    example_links = ExampleLink.query.filter_by(from_id=word_note.id).all()
    example_notes = [
        ExampleNote.query.filter_by(id=link.to_id).first()
        for link in example_links
    ]
    example_dict = await get_usage_example(
        word_note,
        [
            await note.get_display_text(translate=False)
            for note in example_notes
            if note
        ],
    )
    example_note.field1 = example_dict["text"]
    example_note.field2 = example_dict["topic"]

    db.session.commit()

    await ctx.send_message(
        text=format_explanation(await example_note.get_display_text()),
        on_reaction={Emoji.THUMBSDOWN: ExampleDownvoted(example_note.id)},
        new=False,
    )
