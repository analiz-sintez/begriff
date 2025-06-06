import logging
from datetime import datetime, timedelta, timezone
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from ..core import get_user
from ..srs import (
    get_language,
    get_cards,
    get_card,
    record_view_start,
    record_answer,
    Answer,
    Maturity,
)
from ..config import Config
from ..srs import count_new_cards_studied
from .note import format_explanation


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def study_next_card(update: Update, context: CallbackContext) -> None:
    """Fetch a study card for the user and display it with a button to show the answer.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    user = get_user(update.effective_user.username)
    language = get_language(user.get_option("studied_language", "English"))

    logger.info("User %s requested to study.", user.login)

    now = datetime.now(timezone.utc)
    tomorrow = (
        now
        - timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)
        + timedelta(days=1)
    )
    new_cards_remaining = Config.FSRS[
        "new_cards_per_session"
    ] - count_new_cards_studied(user.id, language.id, 12)
    logger.info("%d new cards remaining.", new_cards_remaining)
    cards = get_cards(
        user_id=user.id,
        language_id=language.id,
        end_ts=tomorrow,
        bury_siblings=user.get_option(
            "fsrs/bury_siblings", Config.FSRS["bury_siblings"]
        ),
        randomize=True,
        maturity=(
            None
            if new_cards_remaining > 0
            else [Maturity.YOUNG, Maturity.MATURE]
        ),
    )

    reply_fn = (
        update.callback_query.edit_message_text
        if update.callback_query is not None
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
