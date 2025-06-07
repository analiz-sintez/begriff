import logging
from telegram import Update
from datetime import datetime, timezone

from telegram.ext import CallbackContext
from telegram.constants import ParseMode

from ..core import get_user
from ..srs import (
    get_language,
    Note,
    View,
    Maturity,
    get_notes,
)


logger = logging.getLogger(__name__)


def format_note(note: Note, show_cards: bool = True) -> str:
    """Format a note for display.

    Args:
        note: The note to format.
        show_cards: A flag indicating whether to show card information.

    Returns:
        A formatted string representing the note.
    """
    card_info = f"{note.field1}"
    if show_cards:
        for card in note.cards:
            num_views = View.query.filter_by(card_id=card.id).count()
            days_to_repeat = (
                card.ts_scheduled - datetime.now(timezone.utc)
            ).days
            stability = (
                f"{card.stability:.2f}"
                if card.stability is not None
                else "N/A"
            )
            difficulty = (
                f"{card.difficulty:.2f}"
                if card.difficulty is not None
                else "N/A"
            )
            card_info += f"\n- in {days_to_repeat} days, s={stability} d={difficulty} v={num_views}"
    return card_info


async def list_cards(update: Update, context: CallbackContext) -> None:
    """List all cards, displaying them separately as new, young, and mature along with their stability, difficulty, view counts, and scheduled dates.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    user = get_user(update.effective_user.username)
    language = get_language(user.get_option("studied_language", "English"))
    logger.info(
        "User %s requested to list cards for language %s.",
        user.login,
        language.name,
    )

    new_notes = get_notes(
        user.id, language.id, maturity=[Maturity.NEW], order_by="field1"
    )
    young_notes = get_notes(
        user.id, language.id, maturity=[Maturity.YOUNG], order_by="field1"
    )
    mature_notes = get_notes(
        user.id, language.id, maturity=[Maturity.MATURE], order_by="field1"
    )

    def format_notes(notes, title):
        messages = [
            f"{note_num + 1}: {format_note(note, show_cards=False)}"
            for note_num, note in enumerate(notes)
        ]
        return f"**{title}**\n" + (
            "\n".join(messages) if messages else "No cards"
        )

    new_notes = format_notes(new_notes, "New Notes")
    young_notes = format_notes(young_notes, "Young Notes")
    mature_notes = format_notes(mature_notes, "Mature Notes")

    response_message = f"{new_notes}\n\n{young_notes}\n\n{mature_notes}"

    await update.message.reply_text(
        response_message, parse_mode=ParseMode.MARKDOWN
    )
