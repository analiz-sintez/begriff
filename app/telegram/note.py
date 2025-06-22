import re
import time
import random
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

from telegram import Update
from telegram.ext import CallbackContext

from ..config import Config
from ..core import User
from ..llm import get_explanation, get_base_form, find_mistakes
from ..ui import Signal, bus
from ..srs import (
    Language,
    Maturity,
    get_language,
    create_word_note,
    get_notes,
    update_note,
)
from .router import router
from .utils import authorize, send_message


@dataclass
class WordExplanationRequested(Signal):
    user_id: int
    text: str


@dataclass
class PhraseExplanationRequested(Signal):
    user_id: int
    text: str


@dataclass
class TextExplanationRequested(Signal):
    user_id: int
    text: str


@dataclass
class ExplanationNoteAdded(Signal):
    note_id: int


@dataclass
class ExplanationNoteUpdated(Signal):
    note_id: int


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


def _parse_line(line: str) -> Tuple[Optional[str], Optional[str]]:
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


def _is_note_format(text: str) -> bool:
    """
    Check if every line in the input text is in the format suitable for notes.
    """
    lines = text.strip().split("\n")
    result = all(
        re.match(r"^.{1,200}(?:: .*)?$", line.strip()) for line in lines
    )
    logging.info(f"Message {text} contains notes = {result}")
    return result


@router.message(_is_note_format)
@authorize()
async def add_notes(
    update: Update, context: CallbackContext, user: User
) -> None:
    """Add new word notes or process the input as words with the provided text, explanations, and language.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    message_text = update.message.text.split("\n")
    if len(message_text) > 100:
        return await send_message(
            update, context, "You can add up to 100 words at a time."
        )

    for _, line in enumerate(message_text):
        text, explanation = _parse_line(line)
        if not text:
            await send_message(
                update, context, f"Couldn't parse the text: {line.strip()}"
            )
            continue

        if len(text) <= 12:
            bus.emit(
                WordExplanationRequested(user.id, text),
                update=update,
                context=context,
                explanation=explanation,
            )
        elif len(text) <= 80:
            bus.emit(
                PhraseExplanationRequested(user.id, text),
                update=update,
                context=context,
                explanation=explanation,
            )
        else:
            bus.emit(
                TextExplanationRequested(user.id, text),
                update=update,
                context=context,
                explanation=explanation,
            )


@bus.on(WordExplanationRequested)
@bus.on(PhraseExplanationRequested)
@authorize()
async def add_note(
    update: Update,
    context: CallbackContext,
    user: User,
    text: str,
    explanation: Optional[str] = None,
) -> None:
    """
    Add a note for a user and language. If the note already exists,
    it will update the explanation if provided.
    """

    language = get_language(
        user.get_option(
            "studied_language", Config.LANGUAGE["defaults"]["study"]
        )
    )

    # Convert to base form.
    # TODO: Instead of magic constant, use info about which signal
    # triggered this slot. This requires to pass some context
    # from `bus.emit()` to slots.
    if Config.LLM["convert_to_base_form"] and len(text) <= 12:
        text_base_form = await get_base_form(text, language.name)
        logger.info("Converted %s to base form: %s", text, text_base_form)
        text = text_base_form

    # Check if a note already exists.
    existing_notes = get_notes(
        user_id=user.id, language_id=language.id, text=text
    )
    if existing_notes:
        note = existing_notes[0]
        if explanation:
            note.field2 = explanation
            update_note(note)
            bus.emit(ExplanationNoteUpdated(note.id))
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
    else:
        if not explanation:
            # Get random notes to inject into an explanation.
            # TODO: move it to `get_explanation`, it belongs to its
            # area of responsiblity
            notes_to_inject = None
            if "explanation" in Config.LLM["inject_notes"]:
                notes_to_inject = get_notes_to_inject(user, language)
            # Check if the message is a reply to another message.
            context_message = None
            if update.message.reply_to_message:
                context_message = update.message.reply_to_message.text
            # Ask LLM to explain the word.
            explanation = await get_explanation(
                text,
                language.name,
                notes=notes_to_inject,
                context=context_message,
            )
            logger.info(
                "Fetched explanation for text '%s': '%s'", text, explanation
            )
        note = create_word_note(text, explanation, language.id, user.id)
        bus.emit(ExplanationNoteAdded(note.id))
        logger.info(
            "User %s added a new note with text '%s': '%s'",
            user.login,
            text,
            explanation,
        )

    icon = "🟢" if not existing_notes else "🟡"  # new note: green ball
    explanation = format_explanation(note.field2)
    await send_message(update, context, f"{icon} *{text}* — {explanation}")


@bus.on(TextExplanationRequested)
@authorize()
async def add_text(
    update: Update,
    context: CallbackContext,
    user: User,
    text: str,
    explanation: Optional[str] = None,
):
    language = get_language(
        user.get_option(
            "studied_language", Config.LANGUAGE["defaults"]["study"]
        )
    )
    native_language = get_language(
        user.get_option(
            f"languages/{language.id}/native_language",
            language.name,
            # Config.LANGUAGE["defaults"]["native"],
        )
    )

    reply = await find_mistakes(text, language.name, native_language.name)
    await send_message(update, context, reply)
