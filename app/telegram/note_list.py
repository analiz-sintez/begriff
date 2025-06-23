from dataclasses import dataclass
import logging
import math

from telegram import (
    Update,
    InlineKeyboardButton as Button,
    InlineKeyboardMarkup as Keyboard,
)
from telegram.ext import CallbackContext

from ..config import Config
from ..core import User
from ..srs import (
    get_language,
    Note,
    Maturity,
    get_notes,
    Language,
)
from ..ui import Signal, bus, encode
from .router import router
from .utils import send_message, authorize


logger = logging.getLogger(__name__)


@dataclass
class ListNotesByMaturityRequested(Signal):
    user_id: int
    language_id: int
    maturity_filter: Maturity
    page: int = 1


def format_note_for_list(note: Note) -> str:
    """Format a note for display in the list (field1 only)."""
    return f"{note.field1}"


async def display_notes_by_maturity(
    update: Update,
    context: CallbackContext,
    user: User,
    language: Language,
    maturity_to_display: Maturity,
    page: int = 1,
) -> None:
    """
    Fetches, formats, and displays notes of a specific maturity level
    with a keyboard for maturity selection and pagination.
    """
    all_notes = get_notes(
        user.id,
        language.id,
        maturity=[maturity_to_display],
        order_by="field1",
    )

    notes_per_page = 20
    total_notes = len(all_notes)
    total_pages = math.ceil(total_notes / notes_per_page)
    if total_pages == 0:
        total_pages = 1  # Ensure at least one page even if no notes

    # Ensure page is within valid range
    page = max(1, min(page, total_pages))

    start_index = (page - 1) * notes_per_page
    end_index = start_index + notes_per_page
    notes_on_page = all_notes[start_index:end_index]

    maturity_titles = {
        Maturity.NEW: "New Notes",
        Maturity.YOUNG: "Young Notes",
        Maturity.MATURE: "Mature Notes",
    }
    title = maturity_titles.get(maturity_to_display, "Notes")

    messages = [
        f"{start_index + note_num + 1}. {format_note_for_list(note)}"
        for note_num, note in enumerate(notes_on_page)
    ]
    formatted_notes_section = (
        f"**{title}** ({len(notes_on_page)} of {total_notes} on page {page}/{total_pages}):\n"
        + (
            "\n".join(messages)
            if messages
            else "No notes for this maturity level."
        )
    )

    response_message = formatted_notes_section

    # Maturity selection buttons
    maturity_buttons_row = [
        Button(
            f"{'🆕' if maturity_level == Maturity.NEW else ''}"
            f"{'🌱' if maturity_level == Maturity.YOUNG else ''}"
            f"{'🌳' if maturity_level == Maturity.MATURE else ''} "
            f"{maturity_level.value.capitalize()}",
            callback_data=encode(
                ListNotesByMaturityRequested(
                    user.id,
                    language.id,
                    maturity_level,
                    1,  # Reset to page 1 on maturity change
                )
            ),
        )
        for maturity_level in Maturity
    ]

    all_keyboard_rows = [maturity_buttons_row]

    # Pagination buttons
    if total_pages > 1:
        pagination_buttons_rows = []
        current_page_row = []
        buttons_per_row = 5

        for p_num in range(1, total_pages + 1):
            button_text = f"[{p_num}]" if p_num == page else str(p_num)
            current_page_row.append(
                Button(
                    button_text,
                    callback_data=encode(
                        ListNotesByMaturityRequested(
                            user.id, language.id, maturity_to_display, p_num
                        )
                    ),
                )
            )
            if (
                len(current_page_row) == buttons_per_row
                or p_num == total_pages
            ):
                pagination_buttons_rows.append(current_page_row)
                current_page_row = []

        all_keyboard_rows.extend(pagination_buttons_rows)

    keyboard = Keyboard(all_keyboard_rows) if all_keyboard_rows else None

    await send_message(update, context, response_message, markup=keyboard)


@router.command(
    "list",
    description="List your words, categorized by maturity (New, Young, Mature).",
)
@authorize()
async def list_cards_command(
    update: Update, context: CallbackContext, user: User
) -> None:
    """
    Initial handler for the /list command. Displays 'Young' notes by default, page 1.
    """
    language = get_language(
        user.get_option(
            "studied_language", Config.LANGUAGE["defaults"]["study"]
        )
    )
    if not language:
        await send_message(
            update,
            context,
            "Error: Studied language not set or found. Please set a language using /language.",
        )
        return

    logger.info(
        "User %s requested to list cards for language %s. Defaulting to Young, page 1.",
        user.login,
        language.name,
    )

    await display_notes_by_maturity(
        update, context, user, language, Maturity.YOUNG, page=1
    )


@bus.on(ListNotesByMaturityRequested)
@authorize()
async def handle_list_notes_by_maturity_request(
    update: Update,
    context: CallbackContext,
    user: User,
    language_id: int,
    maturity_filter: Maturity,
    page: int,
) -> None:
    """
    Handles button presses from the maturity or pagination keyboard to display notes.
    """
    language = get_language(language_id)
    if not language:
        logger.error(
            f"Language not found for id {language_id} for user {user.login} in ListNotesByMaturityRequested."
        )
        await send_message(update, context, "Error: Language not found.")
        return

    logger.info(
        "User %s requested to list %s cards for language %s, page %d via button.",
        user.login,
        maturity_filter.value,
        language.name,
        page,
    )

    await display_notes_by_maturity(
        update, context, user, language, maturity_filter, page
    )
