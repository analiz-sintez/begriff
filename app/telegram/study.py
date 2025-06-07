import os
import logging
from datetime import datetime, timedelta, timezone
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto,
)
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from ..core import get_user
from ..srs import (
    get_language,
    get_cards,
    get_card,
    get_view,
    record_view_start,
    record_answer,
    Note,
    Answer,
    Maturity,
    count_new_cards_studied,
    get_notes,
)
from ..llm import translate
from ..image import generate_image
from ..config import Config
from .note import format_explanation
from .router import router


logger = logging.getLogger(__name__)


def get_default_image():
    image_path = generate_image(
        # "A cat teacher in round glasses teaches"
        # " young cat students in a university hall."
        "Stars in the deep night sky."
    )
    return image_path


def get_finish_image():
    image_path = generate_image(
        "A cat teacher in round glasses and his young"
        " cat students celebrate the end of the lection."
    )
    return image_path


async def send_message(
    update: Update,
    context: CallbackContext,
    caption: str,
    markup=None,
):
    """Send or update message, without image."""
    reply_fn = (
        update.callback_query.edit_message_text
        if update.callback_query is not None
        else update.message.reply_text
    )
    await reply_fn(caption, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def send_image_message(
    update: Update,
    context: CallbackContext,
    caption: str,
    image: str = None,
    markup=None,
):
    """Send or update photo message."""
    if not Config.IMAGE["enable"]:
        logging.info("Images in study mode are disabled, ignoring them.")
        await send_message(update, context, caption, markup)
    elif update.callback_query is not None:
        # If the session continues, edit photo object.
        message = (
            update.callback_query.message
            if update.message is None
            else update.message
        )
        if image:
            await message.edit_media(
                media=InputMediaPhoto(
                    media=open(image, "rb"),
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                ),
                reply_markup=markup,
            )
        else:
            await message.edit_caption(
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=markup,
            )
    else:
        # If the session just starts, send photo object.
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(image, "rb") if image else None,
            caption=caption,
            reply_markup=markup,
            parse_mode=ParseMode.MARKDOWN,
        )


def _generate_image_for_note(note: Note) -> str:
    explanation = note.field2
    if not note.language.name == "English":
        explanation = translate(explanation, note.language.name)
        note.set_option("explanation/en", explanation)
    image_path = generate_image(explanation)
    note.set_option("image/path", image_path)
    return image_path


def _get_previous_card(update: Update):
    if update.callback_query is None:
        return None
    query = update.callback_query
    if query.data.startswith("grade:"):
        view_id = int(query.data.split(":")[1])
        return get_view(view_id).card


def _get_image_for_show(card, previous_card):
    note = card.note
    image_path = note.get_option("image/path")
    # Note has image: use it.
    if image_path and os.path.exists(image_path):
        return image_path
    # Note doesn't have image but has leech cards: generate an image.
    if card.is_leech():
        try:
            return _generate_image_for_note(note)
        except:
            logger.warning("Couldn't generate image for note: %s", note)
            return None
    # Note shouldn't have image but previous one has: set default one.
    if not previous_card or previous_card.note.get_option("image/path"):
        return get_default_image()


@router.command("study", "Start a study session")
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

    if not cards:
        logger.info("User %s has no cards to study.", user.login)
        await send_image_message(
            update, context, "All done for today.", get_finish_image()
        )
        return

    card = cards[0]
    image_path = _get_image_for_show(card, _get_previous_card(update))

    keyboard = [
        [InlineKeyboardButton("ANSWER", callback_data=f"answer:{card.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data["current_card_id"] = card.id
    logger.info("Display card front for user %s: %s", user.login, card.front)
    front = format_explanation(card.front)

    await send_image_message(update, context, front, image_path, reply_markup)

    # States: ASK -> ANSWER -> RECORD
    # - ASK: show the front side of the card, wait when user requests
    #   the back side;
    # - ANSWER: show front and back sides, wait for grade (Answer object);
    # - GRADE: got the answer, record it, update card memorization params
    #   and reschedule it.


@router.callback_query("^answer:")
async def handle_study_answer(
    update: Update, context: CallbackContext
) -> None:
    """
    Handle ANSWER button press and show grade buttons.
    """
    user = get_user(update.effective_user.username)
    query = update.callback_query
    user_response = query.data
    await query.answer()  # Acknowledge the callback query
    logger.info("User %s pressed a button: %s", user.login, user_response)

    # ASK -> ANSWER:
    # Show the answer (showing back side of the card)
    card_id = int(user_response.split(":")[1])
    card = get_card(card_id)
    front = format_explanation(card.front)
    back = format_explanation(card.back)
    logger.info(
        "Showing answer for card %s to user %s: %s",
        card.id,
        user.login,
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
    # image_path = card.note.get_option("image/path", get_default_image())
    await send_image_message(
        update, context, f"{front}\n\n{back}", None, reply_markup
    )


@router.callback_query("^grade:")
async def handle_study_grade(update: Update, context: CallbackContext) -> None:
    """
    Handle grade buttons press (AGAIN ... EASY) from user to and record
    the answer.
    """
    user = get_user(update.effective_user.username)
    query = update.callback_query
    user_response = query.data
    await query.answer()  # Acknowledge the callback query
    logger.info("User %s pressed a button: %s", user.login, user_response)

    # ANSWER -> GRADE
    _, view_id, answer_str = user_response.split(":")
    view_id = int(view_id)
    answer = Answer(answer_str)
    logger.info(
        "User %s graded answer %s for view %s",
        user.login,
        answer.name,
        view_id,
    )
    record_answer(view_id, answer)
    await study_next_card(update, context)
