from typing import Any

from dataclasses import dataclass
from nachricht.bus import Signal
from nachricht.messenger import Context

from .. import router
from ..notes import get_note
from ..srs import get_card


@dataclass
class SomethingDownvoted(Signal):
    user_id: int
    message_id: int
    context: str


@dataclass
class SomethingUpvoted(Signal):
    user_id: int
    message_id: int
    context: str


@dataclass
class NegativeFeedbackSent(Signal):
    """A user send negative reaction and wants to leave negative feedback."""

    user_id: str
    text: str
    context: str


@router.command("delete", description="Delete object (use via reply)")
async def _delete_obj(ctx: Context):
    """Show general help for the command."""
    # BUG: if there's no direct handler for "delete" command,
    # the signals for the command with this name won't be emitted
    # since there will be no handler for such a command.
    return await ctx.send_message(
        _(
            """
Use this command to delete a note or other object shown in a message.

As an example:
1. you asked me for a word translation
2. I send it to you and add a note to study
3. you don't want to study it: send /delete as a reply to my message.
        """
        )
    )


@router.command("debug", conditions={"note_id": Any})
@router.authorize()
async def debug_note(ctx: Context, note_id: int):
    note = get_note(note_id)
    debug_info = {
        "note_id": note_id,
        "note": note,
        "cards": note.cards,
    }
    await ctx.send_message(f"```{debug_info}```")


@router.command("debug", conditions={"card_id": Any})
@router.authorize()
async def debug_card(ctx: Context, card_id: int):
    card = get_card(card_id)
    debug_info = {
        "card_id": card_id,
        "card": card,
    }
    await ctx.send_message(f"```{debug_info}```")
