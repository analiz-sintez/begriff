import re
import time
import random
import logging
from typing import Optional, Tuple

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from ..config import Config
from ..core import User, get_user
from ..srs import (
    Note,
    Language,
    Maturity,
    get_language,
    create_word_note,
    get_notes,
    update_note,
)
from ..llm import (
    get_explanation,
    get_base_form,
)


logger = logging.getLogger(__name__)


def format_explanation(explanation: str) -> str:
    """Format an explanation: add newline before brackets, remove them, use /.../, and lowercase the insides of the brackets.

    Args:
        explanation: The explanation string to format.

    Returns:
        The formatted explanation string.
    """
    return re.sub(
        r"\[([^\]]+)\]",
        lambda match: f"\n_{match.group(1).lower()}_",
        explanation,
    )


_notes_to_inject_cache = {}
_cache_time = {}


def get_notes_to_inject(user: User, language: Language) -> list:
    """Retrieve notes to inject for a specific user and language, filtering by maturity and returning a random subset.

    Args:
        user: The user object.
        language: The language object.

    Returns:
        A list of notes for the given user and language, filtered and randomized.
    """
    current_time = time.time()
    cache_key = (user.id, language.id)

    # Invalidate cache if older than 1 minute
    if cache_key in _cache_time and current_time - _cache_time[cache_key] > 60:
        del _notes_to_inject_cache[cache_key]
        del _cache_time[cache_key]

    if cache_key not in _notes_to_inject_cache:
        # Fetch only notes of specified maturity
        notes = get_notes(
            user.id,
            language.id,
            maturity=[
                getattr(Maturity, m.upper())
                for m in Config.LLM["inject_maturity"]
            ],
        )
        # Randomly select inject_count notes
        _notes_to_inject_cache[cache_key] = notes
        _cache_time[cache_key] = current_time

    notes = _notes_to_inject_cache[cache_key]
    random_notes = random.sample(
        notes, min(Config.LLM["inject_count"], len(notes))
    )
    return random_notes


def add_note(
    user: User,
    language: Language,
    text: str,
    explanation: Optional[str] = None,
    context: Optional[str] = None,
) -> Tuple[Note, bool]:
    """Add a note for a user and language. If the note already exists, it will update the explanation if provided.

    Args:
        user: The user object.
        language: The language object.
        text: The text of the note.
        explanation: An optional explanation for the note.

    Returns:
        A tuple containing the note and a boolean indicating if it is a new note.
    """
    existing_notes = get_notes(
        user_id=user.id, language_id=language.id, text=text
    )

    if existing_notes:
        note = existing_notes[0]
        if explanation:
            note.field2 = explanation
            update_note(note)
            logger.info(
                "Updated explanation for text '%s': '%s'",
                text,
                explanation,
            )
        else:
            logger.info(
                "Fetched existing explanation for text '%s': '%s'",
                text,
                note.field2,
            )
        return note, False
    else:
        if not explanation:
            # TODO: move it to `get_explanation`, it belongs to its
            # area of responsiblity
            if "explanation" in Config.LLM["inject_notes"]:
                notes_to_inject = get_notes_to_inject(user, language)
            else:
                notes_to_inject = None
            explanation = get_explanation(
                text,
                language.name,
                notes=notes_to_inject,
                context=context,
            )
            logger.info(
                "Fetched explanation for text '%s': '%s'", text, explanation
            )
        note = create_word_note(text, explanation, language.id, user.id)
        logger.info(
            "User %s added a new note with text '%s': '%s'",
            user.login,
            text,
            explanation,
        )
        return note, True


def __parse_note_line(line: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse a line of text into a word and its explanation, if present.

    Args:
        line: A line of text containing a word and possibly its explanation.

    Returns:
        A tuple containing the word and its explanation.
    """
    match = re.match(
        r"(?P<text>.+?)(?:\s*:\s*(?P<explanation>.*))?$",
        line.strip(),
        re.DOTALL,
    )
    if not match:
        return None, None
    text = match.group("text").strip()
    explanation = (
        match.group("explanation").strip()
        if match.group("explanation")
        else None
    )
    return text, explanation


async def add_notes(update: Update, context: CallbackContext) -> None:
    """Add new word notes or process the input as words with the provided text, explanations, and language.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    user_name = update.effective_user.username
    user = get_user(user_name)
    language = get_language(user.get_option("studied_language", "English"))

    message_text = update.message.text.split("\n")

    if len(message_text) > 200:
        await update.message.reply_text(
            "You can add up to 20 words at a time."
        )
        return

    added_notes = []

    # Check if the message is a reply to another message
    context_message = None
    if update.message.reply_to_message:
        context_message = update.message.reply_to_message.text

    for index, line in enumerate(message_text):
        text, explanation = __parse_note_line(line)
        if not text:
            await update.message.reply_text(
                f"Couldn't parse the text: {line.strip()}"
            )
            continue

        if Config.LLM["convert_to_base_form"]:
            text_base_form = get_base_form(text, language.name)
            logger.info("Converted %s to base form: %s", text, text_base_form)
            text = text_base_form

        # Pass the context to get_explanation if available
        note, is_new = add_note(
            user, language, text, explanation, context=context_message
        )

        icon = "🟢" if is_new else "🟡"  # new note: green ball
        explanation = format_explanation(note.field2)
        added_notes.append(f"{icon} *{text}* — {explanation}")

        # Send each note right after creating it.
        if (index + 1) % 1 == 0:
            await update.message.reply_text(
                "\n".join(added_notes), parse_mode=ParseMode.MARKDOWN
            )
            added_notes = []

    # Send remaining notes if any
    if added_notes:
        await update.message.reply_text(
            "\n".join(added_notes), parse_mode=ParseMode.MARKDOWN
        )
