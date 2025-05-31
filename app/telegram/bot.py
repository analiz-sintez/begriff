import re
import random

# from flask import Config
from ..config import Config
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler,
)
from ..models import Note, User, Language, Answer
from ..service import (
    get_user,
    get_language,
    create_word_note,
    get_view,
    get_views,
    get_card,
    get_cards,
    get_notes,
    update_note,
    record_view_start,
    record_answer,
    get_explanation,
    get_recap,
    count_new_cards_studied,
    Maturity,
)
from datetime import datetime, timezone, timedelta
import logging
from typing import Optional, Tuple

# Set up logging
logging.basicConfig(level=logging.INFO)
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


async def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message to the user when they start the bot.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    logger.info("User %s started the bot.", update.effective_user.id)
    await update.message.reply_text(
        """
Welcome to the Begriff Bot! I'll help you learn new words in a foreign language.
        
Here are the commands you can use:
Simply enter words separated by a newline to add them to your study list with automatic explanations.
/list - See all the words you've added to your study list along with their details.
/study - Start a study session with your queued words.
"""
    )


def __is_note_format(text: str) -> bool:
    """Check if every line in the input text is in the format suitable for notes.

    Args:
        text: The input text to check.

    Returns:
        True if every line is in the note format, otherwise False.
    """
    lines = text.strip().split("\n")
    return all(re.match(r".{1,32}(?::.*)?", line.strip()) for line in lines)


async def router(update: Update, context: CallbackContext) -> None:
    """Route the input text to the appropriate handler.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """

    text = update.message.text
    url_pattern = re.compile(r"https?://\S+")
    last_line = text.strip().split("\n")[-1]
    if url_pattern.match(last_line):
        await process_url(update, context)
    elif __is_note_format(text):
        await add_notes(update, context)
    else:
        await process_text(update, context)


async def process_url(update: Update, context: CallbackContext) -> None:
    user_name = update.effective_user.username
    user = get_user(user_name)
    language = get_language("English")

    if "recap" in Config.LLM["inject_notes"]:
        notes_to_inject = __get_notes_to_inject(user, language)
    else:
        notes_to_inject = None

    last_line = update.message.text.strip().split("\n")[-1]
    recap = get_recap(
        last_line,
        language.name,
        notes=notes_to_inject,
    )
    await update.message.reply_text(recap, parse_mode=ParseMode.MARKDOWN)


async def process_text(update: Update, context: CallbackContext) -> None:
    """Process longer text input.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    # This function will handle longer text inputs
    pass


__notes_to_inject_cache = {}


import time

_notes_to_inject_cache = {}
_cache_time = {}


def __get_notes_to_inject(user: User, language: Language) -> list:
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
            maturity=[Maturity[m] for m in Config.LLM["inject_maturity"]],
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
                notes_to_inject = __get_notes_to_inject(user, language)
            else:
                notes_to_inject = None
            explanation = get_explanation(
                text,
                language.name,
                notes=notes_to_inject,
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
    language = get_language("English")

    message_text = update.message.text.split("\n")

    if len(message_text) > 200:
        await update.message.reply_text(
            "You can add up to 20 words at a time."
        )
        return

    added_notes = []

    for index, line in enumerate(message_text):
        text, explanation = __parse_note_line(line)
        if not text:
            await update.message.reply_text(
                f"Couldn't parse the text: {line.strip()}"
            )
            continue

        note, is_new = add_note(user, language, text, explanation)

        icon = "🟢" if is_new else "🟡"  # new note: green ball
        explanation = format_explanation(note.field2)
        added_notes.append(f"{icon} *{text}* — {explanation}")

        # Send batch of notes every 10 words
        if (index + 1) % 10 == 0:
            await update.message.reply_text(
                "\n".join(added_notes), parse_mode=ParseMode.MARKDOWN
            )
            added_notes = []

    # Send remaining notes if any
    if added_notes:
        await update.message.reply_text(
            "\n".join(added_notes), parse_mode=ParseMode.MARKDOWN
        )


async def study_next_card(update: Update, context: CallbackContext) -> None:
    """Fetch a study card for the user and display it with a button to show the answer.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    user = get_user(update.effective_user.username)
    language = get_language("English")

    logger.info("User %s requested to study.", user.login)
    now = datetime.now(timezone.utc)
    tomorrow = (
        now
        - timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)
        + timedelta(days=1)
    )
    cards = get_cards(
        user_id=user.id,
        language_id=language.id,
        end_ts=tomorrow,
        bury_siblings=True,
        randomize=True,
    )

    reply_fn = (
        update.callback_query.edit_message_text
        if update.callback_query
        else update.message.reply_text
    )

    if not cards:
        logger.info("User %s has no cards to study.", user.login)
        await reply_fn("All done for today.")
        return

    card = cards[0]

    keyboard = [
        [InlineKeyboardButton("ANSWER", callback_data=f"answer:{card.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data["current_card_id"] = card.id
    logger.info("Display card front for user %s: %s", user.id, card.front)
    front = format_explanation(card.front)
    await reply_fn(
        front, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
    )


async def handle_study_session(
    update: Update, context: CallbackContext
) -> None:
    """Handle button press from user to show answers and record responses.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    query = update.callback_query
    user_response = query.data
    await query.answer()  # Acknowledge the callback query
    logger.info(
        "User %s pressed a button: %s", query.from_user.id, user_response
    )

    # States: ASK -> ANSWER -> RECORD
    # - ASK: show the front side of the card, wait when user requests
    #   the back side;
    # - ANSWER: show front and back sides, wait for grade (Answer object);
    # - GRADE: got the answer, record it, update card memorization params
    #   and reschedule it.

    if user_response.startswith("answer:"):
        # ASK -> ANSWER:
        # Show the answer (showing back side of the card)
        card_id = int(user_response.split(":")[1])
        card = get_card(card_id)
        front = format_explanation(card.front)
        back = format_explanation(card.back)
        logger.info(
            "Showing answer for card %s to user %s: %s",
            card.id,
            query.from_user.id,
            back,
        )
        # ... record the moment user started answering
        view_id = record_view_start(card.id)
        # ... prepare the keyboard with memorization quality buttons
        keyboard = [
            [
                InlineKeyboardButton(
                    answer.name,
                    callback_data=f"grade:{view_id}:{answer.value}",
                )
                for answer in Answer
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"{front}\n\n{back}",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
        )

    elif user_response.startswith("grade:"):
        # ANSWER -> GRADE
        _, view_id, answer_str = user_response.split(":")
        view_id = int(view_id)
        answer = Answer(answer_str)
        logger.info(
            "User %s graded answer %s for view %s",
            query.from_user.id,
            answer.name,
            view_id,
        )
        record_answer(view_id, answer)
        await study_next_card(update, context)


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
    logger.info("User %s requested to list cards.", user.login)
    language_id = get_language("English").id

    new_notes = get_notes(
        user.id, language_id, maturity=[Maturity.NEW], order_by="field1"
    )
    young_notes = get_notes(
        user.id, language_id, maturity=[Maturity.YOUNG], order_by="field1"
    )
    mature_notes = get_notes(
        user.id, language_id, maturity=[Maturity.MATURE], order_by="field1"
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


def create_bot(token: str) -> Application:
    """
    Create and configure the Telegram bot application
    with command and callback handlers.

    Args:
        token: The bot token for authentication.

    Returns:
        A configured Application instance representing the bot.
    """
    application = Application.builder().token(token).build()

    # Define bot commands for the menu
    commands = [
        BotCommand("start", "Start using the bot"),
        BotCommand("study", "Start a study session"),
        BotCommand("list", "List all your words"),
    ]

    async def set_commands(application):
        await application.bot.set_my_commands(commands)

    application.post_init = set_commands

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("study", study_next_card))
    application.add_handler(CommandHandler("list", list_cards))

    # MessageHandler for adding words or processing input by default
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, router)
    )

    # CallbackQueryHandler for inline button responses
    application.add_handler(CallbackQueryHandler(handle_study_session))

    return application
