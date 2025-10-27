import logging
import re
from dataclasses import dataclass

from nachricht.auth import User
from nachricht.messenger import Context, Emoji
from nachricht.bus import Signal
from nachricht.i18n import TranslatableString as _
from nachricht.db import db

from app.notes.example_note import add_example_for

from .. import router, bus
from ..notes import get_note, ExampleNote, ExampleLink, examples_for
from ..srs import format_explanation
from ..llm import get_usage_example


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
    example_notes = examples_for(note)

    for example_num in range(3):
        if example_num >= len(example_notes):
            example_note = await add_example_for(note)
        else:
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
    word_note = example_note.get_word()
    example_notes = examples_for(word_note)
    example_dict = await get_usage_example(
        word_note,
        [
            await note.get_display_text(localize=False)
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
