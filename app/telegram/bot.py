import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    record_view_start,
    record_answer,
    get_explanation,
)
from datetime import datetime, timezone, date, timedelta
from ..models import db, User, Answer, Card, View
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message to the user when they start the bot."""
    logger.info("User %s started the bot.", update.effective_user.id)
    await update.message.reply_text(
        "Welcome to the Begriff Bot! "
        "I'll help you learn new words on foreign language."
    )


async def add_note(update: Update, context: CallbackContext):
    """Add a new word note with the provided text, explanation, and language."""
    user_name = update.effective_user.username
    user = get_user(user_name)
    language = get_language("English")

    # Get a word and possibly its explanation from user message.
    message_text = (
        update.message.text.split(" ", 1)[1]
        if len(update.message.text.split(" ", 1)) > 1
        else ""
    )

    match = re.match(
        r"(?P<text>.+?)(?:\s*:\s*(?P<explanation>.*))?$", message_text
    )
    if not match:
        await update.message.reply_text(f"Couldn't parse your text.")
        return

    text = match.group("text").strip()

    # If no explanation provided, generate one with LLM.
    if match.group("explanation"):
        explanation = match.group("explanation").strip()
        logger.info(
            "User provided explanation for text '%s': '%s'", text, explanation
        )
    else:
        explanation = get_explanation(text, language.name)
        logger.info(
            "Fetched explanation for text '%s': '%s'", text, explanation
        )

    logger.info(
        "User %s is adding a note with text '%s':'%s'",
        user_name,
        text,
        explanation,
    )

    # Save note.
    create_word_note(text, explanation, language.id, user.id)
    await update.message.reply_text(
        f"Note added for '{text}' with explanation '{explanation}'."
    )


async def study_next_card(update: Update, context: CallbackContext):
    """Fetch a study card for the user and display it
    with a button to show the answer."""
    user = get_user(update.effective_user.username)
    language = get_language("English")

    logger.info("User %s requested to study.", user.login)
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_start = datetime(
        tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0
    )
    cards = get_cards(
        user_id=user.id,
        language_id=language.id,
        end_ts=tomorrow_start,
        bury_siblings=True,
        randomize=True,
    )

    if not cards:
        logger.info("User %s has no cards to study.", user.login)
        await update.message.reply_text("All done for today.")
        return

    card = cards[0]

    keyboard = [
        [InlineKeyboardButton("ANSWER", callback_data=f"answer:{card.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data["current_card_id"] = card.id
    logger.info("Display card front for user %s: %s", user.id, card.front)
    await update.message.reply_text(card.front, reply_markup=reply_markup)


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
        logger.info(
            "Showing answer for card %s to user %s: %s",
            card.id,
            query.from_user.id,
            card.back,
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
            f"{card.front} - {card.back}", reply_markup=reply_markup
        )

    elif user_response.startswith("grade:"):
        # ANSWER -> GRADE
        _, view_id, answer_str = user_response.split(":")
        answer = Answer(answer_str)
        logger.info(
            "User %s gradeed answer %s for view %s",
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
    # cards = Card.query.filter(Card.note.has(user_id=user.id)).all()
    cards = get_cards(user.id, get_language("English").id)

    if not cards:
        await update.message.reply_text("You have no cards.")
        return

    messages = []
    for card in cards:
        num_views = View.query.filter_by(card_id=card.id).count()
        card_info = (
            "{ts_scheduled}: {front} -> {back} "
            "(id={id}, "
            "s={stability}, "
            "d={difficulty}, "
            "views={views})"
        ).format(
            ts_scheduled=card.ts_scheduled.strftime("%Y-%m-%d %H:%M"),
            front=card.front,
            back=card.back,
            id=card.id,
            stability=(
                f"{card.stability:.2f}"
                if card.stability is not None
                else "N/A"
            ),
            difficulty=(
                f"{card.difficulty:.2f}"
                if card.difficulty is not None
                else "N/A"
            ),
            views=num_views,
        )
        messages.append(card_info)

    await update.message.reply_text("\n\n".join(messages))


def create_bot(token):
    """Create and configure the Telegram bot application with command and callback handlers."""
    application = Application.builder().token(token).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_note))
    application.add_handler(CommandHandler("study", study_next_card))
    application.add_handler(CommandHandler("list", list_cards))

    # CallbackQueryHandler for inline button responses
    application.add_handler(CallbackQueryHandler(handle_user_input))

    # You may need to add more handlers for input validation, not included here.

    return application


# def create_bot(token):
#     """Start the Telegram bot."""
#     application = Application.builder().token(token).build()
#     application.bot.initialize()
#     application.add_handler(CommandHandler('start', start))
#     # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
#     return application
