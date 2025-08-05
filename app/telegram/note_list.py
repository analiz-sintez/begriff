import os
from dataclasses import dataclass
import logging
import math

from telegram import Message

from nachricht.db import db
from nachricht.auth import User
from nachricht.bus import Signal
from nachricht.messenger import Context, Keyboard, Button, Emoji

from .. import bus, router
from ..config import Config
from ..notes import (
    Language,
    get_note,
    get_native_language,
    get_studied_language,
)
from ..srs import (
    Note,
    Maturity,
    get_notes,
    update_note as srs_update_note,
)
from .note import (
    format_explanation,
    NoteDeletionRequested,
    ExampleRequested,
)


logger = logging.getLogger(__name__)


@dataclass
class NotesListRequested(Signal):
    user_id: int
    language_id: int
    maturity_filter: Maturity
    page: int = 1


@dataclass
class NoteSelected(Signal):
    user_id: int
    note_id: int


@dataclass
class NoteTitleEditRequested(Signal):
    user_id: int
    note_id: int


@dataclass
class NoteExplanationEditRequested(Signal):
    user_id: int
    note_id: int


def _format_note_for_list(note: Note) -> str:
    """Format a note for display in the list (field1 only)."""
    return f"{note.field1}"


async def display_notes_by_maturity(
    ctx: Context,
    user: User,
    language: Language,
    maturity_to_display: Maturity,
    page: int = 1,
) -> None:
    """
    Fetches and displays notes of a specific maturity level as keyboard buttons,
    with a keyboard for maturity selection and pagination.
    """
    all_notes = get_notes(
        user.id,
        language.id,
        maturity=[maturity_to_display],
        order_by="field1",
    )

    notes_per_page = 10  # Number of notes to display as buttons per page
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

    response_message = (
        f"**{title}** (Page {page}/{total_pages}, {len(notes_on_page)} of {total_notes} notes shown)\n"
        "Select a note to view details:"
    )
    if not notes_on_page:
        response_message = (
            f"**{title}** (Page {page}/{total_pages})\n"
            "No notes for this maturity level."
        )

    all_keyboard_rows = []

    # Note selection buttons
    for (
        note_item
    ) in notes_on_page:  # Renamed to avoid conflict with note module
        button_text = _format_note_for_list(note_item)
        image_path = note_item.get_option("image/path")
        if (
            Config.IMAGE["enable"]
            and image_path
            and isinstance(image_path, str)
            and os.path.exists(image_path)
        ):
            button_text = f"🖼️ {button_text}"

        note_button = Button(
            text=button_text,
            callback=NoteSelected(user.id, note_item.id),
        )
        all_keyboard_rows.append(
            [note_button]
        )  # Each note button on its own row

    # Maturity selection buttons
    maturity_buttons_row = [
        Button(
            text=f"{'🆕' if maturity_level == Maturity.NEW else ''}"
            f"{'🌱' if maturity_level == Maturity.YOUNG else ''}"
            f"{'🌳' if maturity_level == Maturity.MATURE else ''} "
            f"{maturity_level.value.capitalize()}",
            callback=NotesListRequested(
                user.id,
                language.id,
                maturity_level,
                1,  # Reset to page 1 on maturity change
            ),
        )
        for maturity_level in Maturity
    ]
    if (
        maturity_buttons_row
    ):  # Add if there are maturity levels (should always be true)
        all_keyboard_rows.append(maturity_buttons_row)

    # Pagination buttons
    if total_pages > 1:
        pagination_buttons_rows = []
        current_page_row = []
        buttons_per_row = 8  # Max pagination buttons per row

        # Simple Prev/Next buttons if too many pages, or full list if few
        if total_pages > 2 * buttons_per_row:
            prev_page = max(1, page - 1)
            next_page = min(total_pages, page + 1)
            pagination_row = []
            if page > 1:
                pagination_row.append(
                    Button(
                        text="⬅️ Prev",
                        callback=NotesListRequested(
                            user.id,
                            language.id,
                            maturity_to_display,
                            prev_page,
                        ),
                    )
                )
            pagination_row.append(
                Button(
                    text=f"Page {page}/{total_pages}",
                    callback=NotesListRequested(
                        user.id, language.id, maturity_to_display, page
                    ),
                )
            )  # Non-clickable current page
            if page < total_pages:
                pagination_row.append(
                    Button(
                        text="Next ➡️",
                        callback=NotesListRequested(
                            user.id,
                            language.id,
                            maturity_to_display,
                            next_page,
                        ),
                    )
                )
            if pagination_row:
                all_keyboard_rows.append(pagination_row)

        else:  # Show individual page buttons
            for p_num in range(1, total_pages + 1):
                button_text = f"[{p_num}]" if p_num == page else str(p_num)
                current_page_row.append(
                    Button(
                        text=button_text,
                        callback=NotesListRequested(
                            user.id,
                            language.id,
                            maturity_to_display,
                            p_num,
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

    await ctx.send_message(response_message, markup=keyboard)


@router.command("list", description="List your notes")
@router.authorize()
async def list_cards_command(ctx: Context, user: User) -> None:
    """
    Initial handler for the /list command. Displays 'Young' notes by default, page 1.
    """
    language = get_studied_language(user)
    if not language:
        await ctx.send_message(
            "Error: Studied language not set or found. Please set a language using /language.",
        )
        return

    logger.info(
        "User %s requested to list cards for language %s. Defaulting to Young, page 1.",
        user.login,
        language.name,
    )

    await display_notes_by_maturity(
        ctx, user, language, Maturity.YOUNG, page=1
    )


@bus.on(NotesListRequested)
@router.authorize()
async def handle_list_notes_by_maturity_request(
    ctx: Context,
    user: User,
    language_id: int,
    maturity_filter: Maturity,
    page: int,
) -> None:
    """
    Handles button presses from the maturity or pagination keyboard to display notes.
    """
    language = Language.from_id(language_id)
    if not language:
        logger.error(
            f"Language not found for id {language_id} for user {user.login} in ListNotesByMaturityRequested."
        )
        await ctx.send_message("Error: Language not found.")
        return

    logger.info(
        "User %s requested to list %s cards for language %s, page %d via button.",
        user.login,
        maturity_filter.value,
        language.name,
        page,
    )

    await display_notes_by_maturity(ctx, user, language, maturity_filter, page)


@bus.on(NoteSelected)
@router.authorize()
async def show_note_card(
    ctx: Context,
    user: User,
    note_id: int,
):
    logger.info(f"User {user.login} selected note {note_id}")

    note = get_note(note_id)

    if not note:
        await ctx.send_message("Error: Note not found.", new=True)
        return

    if note.user_id != user.id:
        await ctx.send_message(
            "Error: You can only view details of your own notes.", new=True
        )
        return

    # Prepare explanation details
    original_explanation_raw = note.field2
    original_explanation_formatted = format_explanation(
        original_explanation_raw
    )
    studied_language_name = note.language.name

    explanation_in_native_lang_raw = await note.get_display_text()
    explanation_in_native_lang_formatted = format_explanation(
        explanation_in_native_lang_raw
    )

    message_text_parts = [f"*{note.field1}*"]
    message_text_parts.append(
        f"\n\n_{studied_language_name}_:\n{original_explanation_formatted}"
    )

    if original_explanation_raw != explanation_in_native_lang_raw:
        if native_language := get_native_language(user):
            message_text_parts.append(
                f"\n\n_{native_language.name}_:\n{explanation_in_native_lang_formatted}"
            )
    message_text = "".join(message_text_parts)

    keyboard_buttons = [
        Button(
            "Delete",
            callback=NoteDeletionRequested(user.id, note.id),
        ),
        # Button(
        #     "Edit Title",
        #     callback=NoteTitleEditRequested(user.id, selected_note.id),
        # ),
        # Button(
        #     "Edit Explanation",
        #     callback=NoteExplanationEditRequested(user.id, selected_note.id),
        # ),
    ]
    keyboard = Keyboard([keyboard_buttons])

    reply_to_message: Message | None = None
    if ctx._update.callback_query and ctx._update.callback_query.message:
        reply_to_message = ctx._update.callback_query.message
        try:
            # Acknowledge the button press to remove the loading spinner
            await ctx._update.callback_query.answer()
        except Exception as e:
            logger.warning(f"Failed to answer callback query: {e}")

    # Send a new message replying to the list message (if available)
    image_path = note.get_option("image/path")
    if not (isinstance(image_path, str) and os.path.exists(image_path)):
        image_path = None
    await ctx.send_message(
        text=message_text,
        image=image_path,
        markup=keyboard,
        new=True,  # Always send a new message for note details
        reply_to=reply_to_message,
        on_reaction={
            Emoji.PRAY: ExampleRequested(note_id=note.id),
        },
    )


# @bus.on(NoteTitleEditRequested)
# @router.authorize()
# async def handle_note_title_edit_requested(
#     ctx: Context, user: User, note_id: int
# ):
#     logger.info(
#         f"User {user.login} requested to edit title for note {note_id}"
#     )
#     note_to_edit = get_note(note_id)
#     if not note_to_edit or note_to_edit.user_id != user.id:
#         await ctx.send_message("Error: Note not found or not yours.")
#         return

#     ctx.context(user)["active_edit"] = {
#         "note_id": note_id,
#         "field_to_edit": "field1",
#         "original_message_id": (
#             ctx._update.callback_query.message.message_id
#             if ctx._update.callback_query
#             else None
#         ),
#     }
#     await ctx.send_message("Please send the new title for the note.")
#     if ctx._update.callback_query:
#         await ctx._update.callback_query.answer()


# @bus.on(NoteExplanationEditRequested)
# @router.authorize()
# async def handle_note_explanation_edit_requested(
#     ctx: Context, user: User, note_id: int
# ):
#     logger.info(
#         f"User {user.login} requested to edit explanation for note {note_id}"
#     )
#     note_to_edit = get_note(note_id)
#     if not note_to_edit or note_to_edit.user_id != user.id:
#         await ctx.send_message("Error: Note not found or not yours.")
#         return

#     ctx.context(user)["active_edit"] = {
#         "note_id": note_id,
#         "field_to_edit": "field2",
#         "original_message_id": (
#             ctx._update.callback_query.message.message_id
#             if ctx._update.callback_query
#             else None
#         ),
#     }
#     await ctx.send_message("Please send the new explanation for the note.")
#     if ctx._update.callback_query:
#         await ctx._update.callback_query.answer()


# @router.message(".*")
# @router.authorize()
# async def handle_note_edit_input(ctx: Context, user: User):
#     if not ctx.context(user) or "active_edit" not in ctx.context(user):
#         # This message is not part of an active edit session.
#         # It should be handled by other message handlers (e.g., adding new notes).
#         # The router will try other handlers if this one doesn't "consume" the update.
#         # For now, we simply return, assuming other handlers might pick it up.
#         # If no other handler picks it up, PTB might log an "unhandled update" warning.
#         # A more robust solution might involve ConversationHandler or checking if other handlers exist.
#         logger.debug(
#             "handle_note_edit_input: No active_edit in user_data, passing."
#         )
#         return True  # Indicate that this handler did not fully process the message if it's not an edit.

#     active_edit_info = ctx.context(user)["active_edit"]
#     note_id = active_edit_info["note_id"]
#     field_to_edit = active_edit_info["field_to_edit"]

#     note_to_edit = get_note(note_id)

#     if not note_to_edit:
#         await ctx.send_message("Error: Note not found. Edit cancelled.")
#         del ctx.context(user)["active_edit"]
#         return

#     if note_to_edit.user_id != user.id:
#         await ctx.send_message(
#             "Error: You can only edit your own notes. Edit cancelled.",
#         )
#         del ctx.context(user)["active_edit"]
#         return

#     new_value = ctx.message.text.strip()
#     if not new_value:
#         await ctx.send_message(
#             "The new value cannot be empty. Please try again or send /cancel to abort.",
#         )
#         # Do not clear active_edit, let user try again.
#         return

#     confirmation_message = ""
#     try:
#         if field_to_edit == "field1":
#             old_field1_value = note_to_edit.field1
#             note_to_edit.field1 = new_value
#             # Manually update associated cards' front/back if they used the old field1
#             for card in note_to_edit.cards:
#                 if card.front == old_field1_value:
#                     card.front = new_value
#                 if (
#                     card.back == old_field1_value
#                 ):  # Handles cards where field1 was on the back
#                     card.back = new_value
#             db.session.add(note_to_edit)  # Mark note as dirty
#             db.session.commit()  # Commit note and card changes
#             confirmation_message = f"Note title updated to: '{new_value}'"
#             logger.info(
#                 f"Note {note_id} field1 updated to '{new_value}' by user {user.login}."
#             )

#         elif field_to_edit == "field2":
#             note_to_edit.field2 = new_value
#             # srs_update_note handles card updates well for field2 changes and commits.
#             srs_update_note(note_to_edit)
#             confirmation_message = f"Note explanation updated."
#             logger.info(f"Note {note_id} field2 updated by user {user.login}.")

#         await ctx.send_message(confirmation_message)
#     except Exception as e:
#         db.session.rollback()
#         logger.error(
#             f"Error updating note {note_id} for user {user.login}: {e}",
#             exc_info=True,
#         )
#         await ctx.send_message(
#             "An error occurred while updating the note. Please try again.",
#         )
#     finally:
#         del ctx.context(user)["active_edit"]
#         # To prevent other handlers from processing this message after it's been handled as an edit input:
#         # raise DispatcherHandlerStop(MessageHandler) # This would require importing DispatcherHandlerStop
#         # For simplicity with current router, we assume this is the end of handling for this message.


@bus.on(NoteDeletionRequested)
@router.authorize()
async def handle_note_deletion_requested(
    ctx: Context,
    user: User,
    note_id: int,
):
    logger.info(f"User {user.login} requested deletion of note {note_id}")

    note_to_delete = get_note(note_id)
    if not note_to_delete:
        message = "Error: Note not found or already deleted."
        await ctx.send_message(message)
        return

    if note_to_delete.user_id != user.id:
        message = "Error: You can only delete your own notes."
        await ctx.send_message(message)
        return

    note_field1_for_message = note_to_delete.field1

    try:
        db.session.delete(note_to_delete)
        db.session.commit()
        logger.info(
            f"Note {note_id} ('{note_field1_for_message}') deleted successfully by user {user.login}."
        )
        message = f"Note '{note_field1_for_message}' has been deleted."
        await ctx.send_message(
            message, markup=None
        )  # Remove keyboard from previous message

    except Exception as e:
        db.session.rollback()
        logger.error(
            f"Error deleting note {note_id} for user {user.login}: {e}",
            exc_info=True,
        )
        message = "Error: Could not delete the note."
        await ctx.send_message(message)
