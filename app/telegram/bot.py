import re
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
from ..models import Note, User, Language
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
        "Welcome to the Begriff Bot! I'll help you learn new words in a foreign language.\n\n"
        "Here are the commands you can use:\n"
        "Simply enter words separated by a newline to add them to your study list with automatic explanations.\n"
        "/list - See all the words you've added to your study list along with their details.\n"
        "/study - Start a study session with your queued words."
    )


__notes_to_inject_cache = {}


def __get_notes_to_inject(user: User, language: Language) -> list:
    """Retrieve notes to inject for a specific user and language.

    Args:
        user: The user object.
        language: The language object.

    Returns:
        A list of notes for the given user and language.
    """
    if (user.id, language.id) not in __notes_to_inject_cache:
        __notes_to_inject_cache[(user.id, language.id)] = get_notes(
            user.id,
            language.id,
            maturity=[Maturity.YOUNG, Maturity.MATURE],
        )
    return __notes_to_inject_cache[(user.id, language.id)]


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
            notes_to_inject = __get_notes_to_inject(user, language)
            explanation = get_explanation(text, language.name, notes_to_inject)
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


def __parse_word_line(line: str) -> Tuple[Optional[str], Optional[str]]:
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

    if len(message_text) > 20:
        await update.message.reply_text(
            "You can add up to 20 words at a time."
        )
        return

    added_notes = []

    for line in message_text:
        text, explanation = __parse_word_line(line)
        if not text:
            await update.message.reply_text(
                f"Couldn't parse the text: {line.strip()}"
            )
            continue

        note, is_new = add_note(user, language, text, explanation)

        icon = "✔️" if is_new else ""  # new note: plus sign
        explanation = format_explanation(note.field2)
        added_notes.append(f"*{text}* — {explanation} {icon}")

    if added_notes:
        await update.message.reply_text(
            "\n\n".join(added_notes), parse_mode=ParseMode.MARKDOWN
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


async def handle_user_input(update: Update, context: CallbackContext) -> None:
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
            f"{front}\n\n*{back}*",
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

    new_notes = get_notes(user.id, language_id, maturity=[Maturity.NEW])
    young_notes = get_notes(user.id, language_id, maturity=[Maturity.YOUNG])
    mature_notes = get_notes(user.id, language_id, maturity=[Maturity.MATURE])

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
    """Create and configure the Telegram bot application with command and callback handlers.

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
        MessageHandler(filters.TEXT & ~filters.COMMAND, add_notes)
    )

    # CallbackQueryHandler for inline button responses
    application.add_handler(CallbackQueryHandler(handle_user_input))

    return application
