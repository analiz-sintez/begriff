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
from ..service import (
    get_user,
    get_language,
    create_word_note,
    get_view,
    get_views,
    get_card,
    get_cards,
    get_notes,
    record_view_start,
    record_answer,
    get_explanation,
)
from datetime import datetime, timezone, timedelta
from ..models import User, Answer, Card, View
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def format_explanation(explanation):
    """Format explanation: add newline before brackets, remove them, use /.../, and lowercase the insides of the brackets."""
    return re.sub(
        r"\[([^\]]+)\]",
        lambda match: f"\n_{match.group(1).lower()}_",
        explanation,
    )


async def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message to the user when they start the bot."""
    logger.info("User %s started the bot.", update.effective_user.id)
    await update.message.reply_text(
        "Welcome to the Begriff Bot! I'll help you learn new words in a foreign language.\n\n"
        "Here are the commands you can use:\n"
        "Simply enter words separated by a newline to add them to your study list with automatic explanations.\n"
        "/list - See all the words you've added to your study list along with their details.\n"
        "/study - Start a study session with your queued words."
    )


async def add_note_or_process_input(update: Update, context: CallbackContext):
    """Add new word notes or process the input as words with the provided text, explanations, and language."""
    user_name = update.effective_user.username
    user = get_user(user_name)
    language = get_language("English")

    # Get a list of words and possibly their explanations from user message.
    message_text = update.message.text.split("\n")

    if len(message_text) > 20:
        await update.message.reply_text(
            "You can add up to 20 words at a time."
        )
        return

    added_notes = []

    for line in message_text:
        match = re.match(
            r"(?P<text>.+?)(?:\s*:\s*(?P<explanation>.*))?$",
            line.strip(),
        )
        if not match:
            await update.message.reply_text(
                f"Couldn't parse the text: {line.strip()}"
            )
            continue

        text = match.group("text").strip()

        # Check if a note already exists for this word
        existing_note = get_notes(
            user_id=user.id, language_id=language.id, text=text
        )

        if existing_note:
            explanation = existing_note[0].field2
            logger.info(
                "Fetched existing explanation for text '%s': '%s'",
                text,
                explanation,
            )
        elif match.group("explanation"):
            explanation = match.group("explanation").strip()
            logger.info(
                "User provided explanation for text '%s': '%s'",
                text,
                explanation,
            )
        else:
            explanation = get_explanation(text, language.name)
            logger.info(
                "Fetched explanation for text '%s': '%s'", text, explanation
            )

        explanation = format_explanation(explanation)
        logger.info(
            "User %s is adding a note with text '%s':'%s'",
            user_name,
            text,
            explanation,
        )

        # Save note.
        icon = ""  # existing note: no sign
        if not existing_note:
            create_word_note(text, explanation, language.id, user.id)
            icon = "✔️"  # new note: plus sign
        added_notes.append(f"*{text}* — {explanation} {icon}")

    if added_notes:
        await update.message.reply_text(
            "\n\n".join(added_notes), parse_mode=ParseMode.MARKDOWN
        )


async def study_next_card(update: Update, context: CallbackContext):
    """Fetch a study card for the user and display it with a button to show the answer."""
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


async def handle_user_input(update: Update, context: CallbackContext):
    """Handle button press from user to show answers and record responses."""
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


async def list_cards(update: Update, context: CallbackContext):
    """List all cards with their stability, difficulty, view counts, and scheduled dates."""
    user = get_user(update.effective_user.username)
    logger.info("User %s requested to list cards.", user.login)
    notes = get_notes(user.id, get_language("English").id)

    if not notes:
        await update.message.reply_text("You have no notes.")
        return

    messages = []
    for note_num, note in enumerate(notes):
        card_info = f"{note_num+1}: {note.field1}"
        # for card in note.cards:
        #     num_views = View.query.filter_by(card_id=card.id).count()
        #     days_to_repeat = (
        #         card.ts_scheduled - datetime.now(timezone.utc)
        #     ).days
        #     stability = (
        #         f"{card.stability:.2f}"
        #         if card.stability is not None
        #         else "N/A"
        #     )
        #     difficulty = (
        #         f"{card.difficulty:.2f}"
        #         if card.difficulty is not None
        #         else "N/A"
        #     )
        #     card_info += f"\n- in {days_to_repeat} days, s={stability} d={difficulty} v={num_views}"

        messages.append(card_info)

    await update.message.reply_text(
        "\n".join(messages), parse_mode=ParseMode.MARKDOWN
    )


def create_bot(token):
    """Create and configure the Telegram bot application with command and callback handlers."""
    application = Application.builder().token(token).build()

    # Define bot commands for the menu
    commands = [
        BotCommand("start", "Start using the bot"),
        BotCommand("study", "Start a study session"),
        BotCommand("list", "List all your words"),
    ]

    async def set_commands():
        await application.bot.set_my_commands(commands)

    # application.run_task(set_commands())

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("study", study_next_card))
    application.add_handler(CommandHandler("list", list_cards))

    # MessageHandler for adding words or processing input by default
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND, add_note_or_process_input
        )
    )

    # CallbackQueryHandler for inline button responses
    application.add_handler(CallbackQueryHandler(handle_user_input))

    return application
