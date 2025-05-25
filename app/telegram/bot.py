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
    record_view_start,
    record_answer,
    get_explanation,
)
from datetime import datetime, timezone
from ..models import db, User, Answer
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


async def add(update: Update, context: CallbackContext):
    """Add a new word note with the provided text, explanation, and language."""
    user_name = update.effective_user.username
    user = get_user(user_name)
    language = get_language("English")

    message_text = (
        update.message.text.split(" ", 1)[1]
        if len(update.message.text.split(" ", 1)) > 1
        else ""
    )

    # Using regex to extract text and explanation, making explanation optional
    match = re.match(
        r"(?P<text>.+?)(?:\s*:\s*(?P<explanation>.*))?$", message_text
    )
    if not match:
        await update.message.reply_text(f"Couldn't parse your text.")
        return

    text = match.group("text").strip()

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
    create_word_note(text, explanation, language.id, user.id)
    await update.message.reply_text(
        f"Note added for '{text}' with explanation '{explanation}'."
    )


async def study(update: Update, context: CallbackContext):
    """Fetch a study card for the user and display it
    with a button to show the answer."""
    user = get_user(update.effective_user.username)
    language = get_language("English")

    logger.info("User %s requested to study.", user.login)
    views = get_views(user_id=user.id, language_id=language.id)

    if not views:
        logger.info("User %s has no cards to study.", user.login)
        await update.message.reply_text("All done for today.")
        return

    view = views[0]
    card = view.card

    keyboard = [
        [InlineKeyboardButton("ANSWER", callback_data=f"answer:{view.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data["current_view_id"] = view.id
    logger.info("Display card front for user %s: %s", user.id, card.front)
    await update.message.reply_text(card.front, reply_markup=reply_markup)


async def button(update: Update, context: CallbackContext):
    """Handle button press from user to show answers and record responses."""
    query = update.callback_query
    user_response = query.data
    await query.answer()  # Acknowledge the callback query
    logger.info(
        "User %s pressed a button: %s", query.from_user.id, user_response
    )

    if user_response.startswith("answer:"):
        view_id = int(user_response.split(":")[1])
        # Show the answer (showing back side of the card)
        keyboard = [
            [
                InlineKeyboardButton(
                    answer.name,
                    callback_data=f"record:{view_id}:{answer.value}",
                )
                for answer in Answer
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        view = get_view(view_id)
        card = view.card
        logger.info(
            "Showing answer for card %s to user %s: %s",
            card.id,
            query.from_user.id,
            card.back,
        )
        await query.edit_message_text(
            f"{card.front} - {card.back}", reply_markup=reply_markup
        )

    elif user_response.startswith("record:"):
        _, view_id, answer_str = user_response.split(":")
        answer = Answer(answer_str)
        logger.info(
            "User %s recorded answer %s for view %s",
            query.from_user.id,
            answer.name,
            view_id,
        )
        await study_next_card(update, context, int(view_id), answer)


async def study_next_card(
    update: Update, context: CallbackContext, view_id: int, user_answer: Answer
):
    """Record the user's answer and show the next card."""
    user = get_user(update.effective_user.username)
    logger.info(
        "Recording answer for user %s on view %d as %s",
        user.id,
        view_id,
        user_answer.name,
    )
    record_answer(view_id, user_answer)

    # Get the next scheduled view
    language = get_language("English")

    views = get_views(
        user_id=user.id,
        language_id=language.id,
        answers=[None],
        end_ts=datetime.now(),
    )
    query = update.callback_query

    if not views:
        logger.info("User %s has completed all scheduled cards.", user.id)
        await query.edit_message_text("All done for today.")
        return

    view = views[0]
    card = view.card

    keyboard = [
        [InlineKeyboardButton("ANSWER", callback_data=f"answer:{view.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.info("Display next card front for user %s: %s", user.id, card.front)
    await query.edit_message_text(card.front, reply_markup=reply_markup)


def create_bot(token):
    """Create and configure the Telegram bot application with command and callback handlers."""
    application = Application.builder().token(token).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("study", study))

    # CallbackQueryHandler for inline button responses
    application.add_handler(CallbackQueryHandler(button))

    # You may need to add more handlers for input validation, not included here.

    return application


# def create_bot(token):
#     """Start the Telegram bot."""
#     application = Application.builder().token(token).build()
#     application.bot.initialize()
#     application.add_handler(CommandHandler('start', start))
#     # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
#     return application
