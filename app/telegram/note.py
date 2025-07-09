import re
import time
import random
import logging

from typing import Optional, Tuple, Any
from dataclasses import dataclass

from core.auth import User
from core.bus import Signal
from core.messenger import Context

from .. import bus, router
from ..config import Config
from ..llm import get_explanation, get_base_form, find_mistakes, translate
from ..srs import (
    Language,
    Maturity,
    get_language,
    create_word_note,
    get_notes,
    get_note,
    update_note,
    Note,
)


@dataclass
class WordExplanationRequested(Signal):
    user_id: int
    text: str
    explanation: Optional[str] = None


@dataclass
class PhraseExplanationRequested(Signal):
    user_id: int
    text: str
    explanation: Optional[str] = None


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


async def get_explanation_in_native_language(note: Note) -> str:
    """
    Get the explanation of a note translated into the user's selected native language
    for the note's studied language. Caches the translation in note options.

    Args:
        note: The Note object.

    Returns:
        The explanation string, translated if necessary.
    """
    user = note.user
    studied_language = note.language

    # Determine the native language ID for this studied language
    native_language_id = user.get_option(
        f"languages/{studied_language.id}/native_language"
    )

    # Fallback if native language ID is not set for some reason, though UI should prevent this.
    if native_language_id is None:
        logger.warning(
            f"Native language not set for studied language {studied_language.name} (ID: {studied_language.id}) for user {user.login}. Defaulting to studied language."
        )
        native_language_id = studied_language.id

    # If studied language is the native language, no translation needed.
    if native_language_id == studied_language.id:
        return note.field2

    native_language = get_language(native_language_id)
    if not native_language:
        logger.error(
            f"Could not find native language with ID {native_language_id} for user {user.login}. Returning original explanation."
        )
        return note.field2

    # Check cache in note options
    translation_option_key = f"translations/{native_language.id}"
    cached_translation = note.get_option(translation_option_key)

    if cached_translation is not None and isinstance(cached_translation, str):
        logger.info(
            f"Found cached translation for note {note.id} to native language {native_language.name}."
        )
        return cached_translation

    # If no cached translation, translate and save
    original_explanation = note.field2
    if not original_explanation:  # Handle empty original explanation
        return ""

    logger.info(
        f"Translating explanation for note {note.id} from {studied_language.name} to {native_language.name}."
    )
    try:
        translated_explanation = await translate(
            original_explanation,
            src_language=studied_language.name,
            dst_language=native_language.name,
        )
        # Save to note options
        note.set_option(translation_option_key, translated_explanation)
        logger.info(
            f"Saved new translation for note {note.id} to native language {native_language.name}."
        )
        return translated_explanation
    except Exception as e:
        logger.error(
            f"Error translating explanation for note {note.id}: {e}. Returning original."
        )
        return original_explanation


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
        re.match(r"^[^/]{1,200}(?:: .*)?$", line.strip()) for line in lines
    )
    logging.info(f"Message {text} contains notes = {result}")
    return result


@router.message(_is_note_format)
@router.authorize()
async def add_notes(ctx: Context, user: User) -> None:
    """Add new word notes or process the input as words with the provided text, explanations, and language.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    message_text = ctx.update.message.text.split("\n")
    if len(message_text) > 100:
        return await ctx.send_message("You can add up to 100 words at a time.")

    for _, line in enumerate(message_text):
        text, explanation = _parse_line(line)
        if not text:
            await ctx.send_message(f"Couldn't parse the text: {line.strip()}")
            continue

        if len(text) <= 12:
            bus.emit(
                WordExplanationRequested(user.id, text, explanation), ctx=ctx
            )
        elif len(text) <= 30:
            bus.emit(
                PhraseExplanationRequested(user.id, text, explanation), ctx=ctx
            )
        else:
            bus.emit(TextExplanationRequested(user.id, text), ctx=ctx)


@bus.on(WordExplanationRequested)
@bus.on(PhraseExplanationRequested)
@router.authorize()
async def add_note(
    ctx: Context,
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
            if ctx.update.message.reply_to_message:
                context_message = ctx.update.message.reply_to_message.text
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
    display_explanation = format_explanation(
        await get_explanation_in_native_language(note)
    )
    message = await ctx.send_message(
        f"{icon} *{text}* — {display_explanation}"
    )
    # Save an association between the note and the message.
    # TODO Here is a buggy piece: we either need to check if there's something
    # in the message context, or we are at risk to erase the early state when
    # we edit the message.
    # Possible solutions:
    # - make ctx.message_context clever;
    # - make send_message accept `context` arg and set context only on send.
    ctx.message_context[message.message_id] = {"note_id": note.id}


@router.reaction(["👎"], message_context={"note_id": Any})  # finger down
@router.authorize()
async def handle_negative_reaction(ctx: Context, user: User, reply_to: object):
    """
    Handles a negative reaction on a note's explanation message.
    It regenerates the explanation, updates the note, and sends a new message.
    """
    message_ctx = ctx.message_context.get(reply_to.message_id)
    note_id = message_ctx.get("note_id")
    if not (note := get_note(note_id)):
        return
    if note.user_id != user.id:
        return

    logger.info(
        f"User {user.login} disliked the explanation for note {note.id}. Regenerating."
    )

    # Regenerate the explanation, similar to creating a new one
    notes_to_inject = None
    if "explanation" in Config.LLM["inject_notes"]:
        notes_to_inject = get_notes_to_inject(user, note.language)

    # We don't have the original message context (like a reply-to) on reaction, so pass None
    new_explanation = await get_explanation(
        note.field1, note.language.name, notes=notes_to_inject, context=None
    )

    # Update the note with the new explanation
    note.field2 = new_explanation
    update_note(note)
    bus.emit(ExplanationNoteUpdated(note.id))
    logger.info(
        f"Updated explanation for note {note.id} for user {user.login} to: '{new_explanation}'"
    )

    # Send the new explanation to the user as a new message
    icon = "🟡"  # Regenerated note: yellow ball
    display_explanation = format_explanation(
        await get_explanation_in_native_language(note)
    )
    new_message = await ctx.send_message(
        f"{icon} *{note.field1}* — {display_explanation}",
        new=True,  # Ensure it's a new message
    )

    # Update the message map to associate the new message with the note
    # so the user can react to the new explanation as well.
    if new_message:
        ctx.message_context[new_message.message_id] = {"note_id": note.id}


@bus.on(TextExplanationRequested)
@router.authorize()
async def add_text(
    ctx: Context,
    user: User,
    text: str,
    explanation: Optional[str] = None,
):
    language = get_language(
        user.get_option(
            "studied_language", Config.LANGUAGE["defaults"]["study"]
        )
    )
    native_language_id = user.get_option(
        f"languages/{language.id}/native_language",
        default_value=language.id,  # Fallback
    )
    native_language = (
        get_language(native_language_id) if native_language_id else language
    )

    reply = await find_mistakes(text, language.name, native_language.name)
    await ctx.send_message(reply)


# #################### Prototyping the interface ####################


# # just a slot: already implemented
# @bus.on(EmojiSent)
# async def handle_reaction(emoji):
#     if emoji is ':)':
#         pass
#     elif emoji is ':(':
#         pass

# # a slot with a condition on signal parameter: need to implement
# @bus.on(EmojiSent, emoji=':)')
# async def handle_positive_reaction(emoji):
#     # record
#     pass

# @bus.on(EmojiSent, emoji=':(')
# async def handle_negative_reaction(emoji):
#     # record and regenerate
#     pass

# # a reaction handler dispatching reactions
# @router.reaction()
# async def dispatch_reactions(ctx):
#     emoji = ctx.emoji
#     bus.emit(EmojiSent(emoji), ctx=ctx)

# # a command that dispatches the action
# @router.command("del")
# async def handle_del(ctx):
#     reply_to = ctx.reply_to
#     if reply_to is Note:
#         bus.emit(NoteDeletionRequested(note_id=reply_to.id))
#     elif reply_to is Recap:
#         bus.emit(RecapDeletionRequested(note_id=reply_to.id))
