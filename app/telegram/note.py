import re
import logging

from typing import Optional, Tuple, Any, List, Dict, Union
from dataclasses import dataclass

from nachricht.llm import query_llm
from nachricht.auth import User
from nachricht.bus import Signal
from nachricht.messenger import Context, Emoji
from nachricht.i18n import TranslatableString as _

from .. import bus, router
from ..llm import (
    get_explanation,
    get_base_form,
    find_mistakes,
    translate,
    detect_language,
)
from ..notes import (
    language_code_by_name,
    get_language,
    Language,
    get_native_language,
    get_studied_language,
)
from ..srs import (
    create_word_note,
    get_card,
    get_notes,
    get_note,
    update_note,
    Note,
    get_notes_to_inject,
    format_explanation,
)

from .translate import TranslationRequested


logger = logging.getLogger(__name__)


################################################################
# Handling User Input & Creating New Notes


@dataclass
class WordExplanationRequested(Signal):
    user_id: int
    field1: str
    field2: Optional[str] = None


@dataclass
class ExplanationNoteAdded(Signal):
    """New note with an explanation of the word was created."""

    note_id: int


@dataclass
class ExplanationNoteShown(Signal):
    """New note with an explanation of the word was shown to the user."""

    note_id: int


@dataclass
class ExplanationNoteUpdated(Signal):
    """A note was updated by teh user."""

    note_id: int


@dataclass
class NoteDeletionRequested(Signal):
    """User requested to delete a note."""

    user_id: int
    note_id: int


@dataclass
class UserInputProcessed(Signal):
    """All notes found in the user input were processed."""

    user_id: int


@dataclass
class NoteUpvoted(Signal):
    """A user set a positive reaction to the note."""

    note_id: int


@dataclass
class NoteDownvoted(Signal):
    """A user set a negative reaction to the note."""

    note_id: int


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
        re.match(r"^[^/!?]{2}.{1,200}(?:: .*)?$", line.strip())
        for line in lines
    ):
        logging.info(f"Message {text} contains notes.")
        return {"notes": lines}
    return None


@router.message(_is_note_format)
@router.authorize()
async def dispatch_user_input(
    ctx: Context, user: User, notes: List[str]
) -> None:
    """Add new word notes or process the input as words with the provided text, explanations, and language.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    if len(notes) > 100:
        return await ctx.send_message(
            _("You can add up to 100 words at a time.")
        )

    studied_language = get_studied_language(user)
    native_language = get_native_language(user)

    for _, line in enumerate(notes):
        field1, field2 = _parse_line(line)
        if not field1:
            await ctx.send_message(f"Couldn't parse the text: {line.strip()}")
            continue

        if ctx.config.UX["guess_input_language"]:
            # Try to guess if a user wants to translate from their native language.
            guess = detect_language(
                field1, [studied_language.name, native_language.name]
            )
            text_language_name = guess.language.name.lower()
            if (
                text_language_name != studied_language.name.lower()
                and guess.value
                >= ctx.config.UX["guess_input_language_threshold"]
            ):
                if code := language_code_by_name(text_language_name):
                    text_language = get_language(text_language_name)
                    await bus.emit_and_wait(
                        TranslationRequested(
                            user.id,
                            src_language_id=text_language.id,
                            dst_language_id=studied_language.id,
                            text=field1,
                        ),
                        ctx=ctx,
                    )
                continue

        if len(field1) <= 30:
            await bus.emit_and_wait(
                WordExplanationRequested(user.id, field1, field2), ctx=ctx
            )
        else:
            await bus.emit_and_wait(
                GrammarCheckRequested(user.id, field1), ctx=ctx
            )
    await bus.emit_and_wait(UserInputProcessed(user.id), ctx=ctx)


@bus.on(WordExplanationRequested)
@router.authorize()
async def add_note(
    ctx: Context,
    user: User,
    field1: str,
    field2: Optional[str] = None,
) -> None:
    """
    Add a note for a user and language. If the note already exists,
    it will update the explanation if provided.
    """
    studied_language = get_studied_language(user)
    native_language = get_native_language(user)

    # Convert to base form.
    # TODO: Instead of magic constant, use info about which signal
    # triggered this slot. This requires to pass some context
    # from `bus.emit()` to slots.
    word = field1
    if ctx.config.LLM["convert_to_base_form"] and len(field1) <= 12:
        field1_base_form = await get_base_form(field1, studied_language.name)
        logger.info("Converted %s to base form: %s", field1, field1_base_form)
        word = field1_base_form

    needs_update = False
    explanation = None
    translation = None

    translation_key = f"translations/{native_language.code}"

    note = None
    existing_notes = get_notes(
        user_id=user.id, language_id=studied_language.id, text=word
    )
    if existing_notes:
        note = existing_notes[0]
        explanation = note.field1
        translation = note.get_option(translation_key)

    # If the user provided field2, then treat if according to how
    # the languages are set up:
    if field2:
        needs_update = True
        # ... if studying language is the same as the native one —
        #     it is an explanation
        if studied_language == native_language:
            explanation = field2
        # ... if not — it is translation
        else:
            translation = field2

    # Generate what's missing
    if not explanation:
        notes_to_inject = None
        if "explanation" in ctx.config.LLM["inject_notes"]:
            notes_to_inject = get_notes_to_inject(user, studied_language)
        # Check if the message is a reply to another message.
        context_message = None
        if ctx.message.parent:
            context_message = ctx.message.parent.text
        # Ask LLM to explain the word in user's studied language.
        explanation = await get_explanation(
            word,
            studied_language.name,
            notes=notes_to_inject,
            context=context_message,
        )
        logger.info(
            "Generated an explanation for text '%s': '%s'", word, explanation
        )
        needs_update = True

    if studied_language != native_language and not translation:
        translation = await translate(
            word,
            src_language=studied_language.name,
            dst_language=native_language.name,
        )
        logger.info(
            "Generated a translation for text '%s': '%s'", word, translation
        )
        needs_update = True

    if note:
        if needs_update:
            note.field2 = explanation
            note.set_option(translation_key, translation)
    else:
        note = create_word_note(
            word, explanation, studied_language.id, user.id
        )
        note.set_option(translation_key, translation)
        bus.emit(ExplanationNoteAdded(note.id))
        logger.info(
            "User %s added a new note: '%s', translation='%s', explanation='%s'",
            user.login,
            word,
            translation,
            explanation,
        )

    icon = "🟢" if not existing_notes else "🟡"  # new note: green ball
    display_text = format_explanation(await note.get_display_text())
    message = await ctx.send_message(
        f"{icon} *{word}* — {display_text}",
        reply_to=None,
        on_reaction={
            Emoji.THUMBSDOWN: NoteDownvoted(note_id=note.id),
            Emoji.PRAY: ExamplesRequested(note_id=note.id),
        },
        on_command={
            "delete": NoteDeletionRequested(user_id=user.id, note_id=note.id),
        },
    )
    bus.emit(ExplanationNoteShown(note.id), ctx=ctx)
    return message


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
    display_explanation = format_explanation(await note.get_display_text())
    new_message = await ctx.send_message(
        f"{icon} *{note.field1}* — {display_explanation}",
        new=True,  # Ensure it's a new message
        on_reaction={
            Emoji.THUMBSDOWN: NoteDownvoted(note_id=note.id),
            Emoji.PRAY: ExamplesRequested(note_id=note.id),
        },
        on_command={
            "delete": NoteDeletionRequested(user_id=user.id, note_id=note.id),
        },
    )


################################################################
# Grammar check


@dataclass
class GrammarCheckRequested(Signal):
    """A user asked to check the phrase or sentence for the grammar errors."""

    user_id: int
    text: str


@dataclass
class GrammarCheckSent(Signal):
    """The user text was checked for the grammar errors and the reply was sent."""

    user_id: int
    text: str


@dataclass
class GrammarCheckDownvoted(Signal):
    """The user disliked the grammar check we sent them."""

    user_id: int
    text: str


@router.command(
    "check", ["text"], description=_("Check a phrase for grammar mistakes")
)
@router.authorize()
async def _check_sentence_for_mistakes(
    ctx: Context,
    user: User,
    text: Optional[str] = None,
):
    if not text:
        return await ctx.send_message(
            _(
                """
Send me a phrase or a sentence, and I'll check it for grammatic or other mistakes.
        """
            )
        )
    bus.emit(GrammarCheckRequested(user.id, text), ctx=ctx)


@bus.on(GrammarCheckRequested)
@router.authorize()
async def check_sentence_for_mistakes(
    ctx: Context,
    user: User,
    text: str,
    explanation: Optional[str] = None,
):
    language = get_studied_language(user)
    native_language = get_native_language(user)

    reply = await find_mistakes(text, language.name, native_language.name)
    message = await ctx.send_message(
        reply,
        on_reaction={
            Emoji.THUMBSDOWN: GrammarCheckDownvoted(user.id, text),
            Emoji.PRAY: GrammarCheckRequested(user.id, text),
        },
    )
    bus.emit(GrammarCheckSent(user.id, text), ctx=ctx)
    return message


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


@dataclass
class ExamplesDownvoted(Signal):
    """The user downvoted usage examples we sent to them."""

    note_id: int


async def get_usage_examples(note: Note, ctx: Context):
    language = Language.from_id(note.language_id)
    native_language = get_native_language(note.user)
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
@bus.on(ExamplesDownvoted)
@router.authorize()
async def give_usage_examples(ctx: Context, user: User, note_id: int) -> None:
    if not (note := get_note(note_id)):
        return

    try:
        examples = await get_usage_examples(note, ctx)
        response = format_explanation(examples)
    except Exception as e:
        logging.error(f"Got error while making examples: {e}")
        response = _("Couldn't make examples, sorry.")

    await ctx.send_message(
        text=response,
        reply_to=ctx.message,
        on_reaction={Emoji.THUMBSDOWN: ExamplesRequested(note.id)},
    )
    bus.emit(ExamplesSent(note.id))
