import re
import time
import random
import logging

from typing import Optional, Tuple, Any, List, Dict, Union
from dataclasses import dataclass

from app.srs.service import get_card
from core.llm import query_llm
from core.auth import User
from core.bus import Signal
from core.messenger import Context
from core.i18n import TranslatableString as _

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


@dataclass
class NoteDeletionRequested(Signal):
    user_id: int
    note_id: int


@dataclass
class NoteUpvoted(Signal):
    """A user set a positive reaction to the note."""

    note_id: int


@dataclass
class NoteDownvoted(Signal):
    """A user set a negative reaction to the note."""

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
    native_language_id = user.get_option(f"native_language")

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
    translation_option_key = f"explanations/{native_language.code}"
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


def _is_note_format(text: str) -> Optional[Dict]:
    """
    Check if every line in the input text is in the format suitable for notes.
    """
    lines = text.strip().split("\n")
    if all(
        re.match(r"^[^/!?]{1,200}(?:: .*)?$", line.strip()) for line in lines
    ):
        logging.info(f"Message {text} contains notes.")
        return {"notes": lines}
    return None


@router.message(_is_note_format)
@router.authorize()
async def add_notes(ctx: Context, user: User, notes: List[str]) -> None:
    """Add new word notes or process the input as words with the provided text, explanations, and language.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    if len(notes) > 100:
        return await ctx.send_message(
            _("You can add up to 100 words at a time.")
        )

    for _, line in enumerate(notes):
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


@router.command("examples", conditions={"note_id": Any})
@router.authorize()
async def get_usage_examples(ctx: Context, note_id: int):
    pass


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
    defaults = ctx.config.LANGUAGE["defaults"]
    language = get_language(
        user.get_option("studied_language", defaults["study"])
    )
    native_language = get_language(
        user.get_option("native_language", defaults["native"])
    )

    # Convert to base form.
    # TODO: Instead of magic constant, use info about which signal
    # triggered this slot. This requires to pass some context
    # from `bus.emit()` to slots.
    if ctx.config.LLM["convert_to_base_form"] and len(text) <= 12:
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
            if "explanation" in ctx.config.LLM["inject_notes"]:
                notes_to_inject = get_notes_to_inject(user, language)
            # Check if the message is a reply to another message.
            context_message = None
            if ctx.message.parent:
                context_message = ctx.message.parent.text
            # Ask LLM to explain the word in user's studied language.
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
        # Ask LLM to translate the word into user's native language.
        translation = await translate(
            text,
            src_language=language.name,
            dst_language=native_language.name,
        )
        note.set_option(f"translations/{native_language.code}", translation)

    icon = "🟢" if not existing_notes else "🟡"  # new note: green ball
    display_explanation = format_explanation(
        await get_explanation_in_native_language(note)
    )
    return await ctx.send_message(
        f"{icon} *{text}* — {display_explanation}",
        reply_to=None,
        on_reaction={
            "👎": NoteDownvoted(note_id=note.id),  # finger down
            "🙏": ExamplesRequested(note_id=note.id),  # :prey:
        },
        on_command={
            "delete": NoteDeletionRequested(user_id=user.id, note_id=note.id),
        },
    )


@bus.on(NoteDownvoted)
@router.authorize()
async def handle_negative_reaction(
    ctx: Context, user: User, reply_to: object, note_id: int
):
    """
    Handles a negative reaction on a note's explanation message.
    It regenerates the explanation, updates the note, and sends a new message.
    """
    if not (note := get_note(note_id)):
        return
    if note.user_id != user.id:
        return

    logger.info(
        f"User {user.login} disliked the explanation for note {note.id}. Regenerating."
    )

    # Regenerate the explanation, similar to creating a new one
    notes_to_inject = None
    if "explanation" in ctx.config.LLM["inject_notes"]:
        notes_to_inject = get_notes_to_inject(user, note.language)

    # We don't have the original message context (like a reply-to) on reaction, so pass None
    new_explanation = await get_explanation(
        note.field1, note.language.name, notes=notes_to_inject, context=None
    )

    # Update the note with the new explanation.
    note.field2 = new_explanation
    # Clear translated explanations cache.
    note.set_option("explanations", {})
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
        on_reaction={
            "👎": NoteDownvoted(note_id=note.id),
            "🙏": ExamplesRequested(note_id=note.id),  # :prey:
        },
        on_command={
            "delete": NoteDeletionRequested(user_id=user.id, note_id=note.id),
        },
    )


################################################################
# Examples
@dataclass
class ExamplesRequested(Signal):
    """User requested usage examples for a note."""

    note_id: int


@dataclass
class ExamplesSent(Signal):
    """Usage examples for a note sent to the user."""

    note_id: int


async def get_usage_examples(note: Note):
    language = get_language(note.language_id)
    defaults = Config.LANGUAGE["defaults"]
    native_language = get_language(
        note.user.get_option("native_language", defaults["native"])
    )
    return await query_llm(
        f"""
You are {language.name} tutor helping a student to learn new language. Their native language is {native_language.name}.

Generate three usage examples for the given word or phrase.

- Examples should be full sentencts.
- If a word has multiple different meanings, provide examples showing those meanings. Indicate this meaning in square brackets in student's native language.

The pattern: the student studies German and their native language is English, the word is: "Konto".

Your response:
        
"[Bank account] Ich habe ein neues Konto bei der Bank eröffnet, um mein Geld sicher zu verwalten.
[Bank account] Bitte überweise den Betrag auf mein Konto bis Ende des Monats.
[User account] Er hat ein Konto bei einem Online-Dienst, um Filme zu streamen."
        """,
        note.field1,
    )


@bus.on(ExamplesRequested)
@router.authorize()
async def give_usage_examples(ctx: Context, user: User, note_id: int) -> None:
    if not (note := get_note(note_id)):
        return

    try:
        examples = await get_usage_examples(note)
        response = format_explanation(examples)
    except Exception as e:
        logging.error(f"Got error while making examples: {e}")
        response = _("Couldn't make examples, sorry.")

    await ctx.send_message(
        text=response,
        reply_to=ctx.message,
        on_reaction={"👎": ExamplesRequested(note.id)},
    )
    bus.emit(ExamplesSent(note.id))


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
