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
    Answer,
    Maturity,
    count_new_cards_studied,
    get_notes,
)
from ..llm import translate
from ..image import generate_image
from ..config import Config
from .note import format_explanation


logger = logging.getLogger(__name__)


async def _generate_images(user, language):
    """
    Generate images for YOUNG notes that have at least one leech card using the image.generate_image function.
    """
    logger.info(
        "Starting image generation process for YOUNG notes with leech cards."
    )
    notes = get_notes(
        user_id=user.id,
        language_id=language.id,
        maturity=[Maturity.YOUNG],
    )

    for note in notes:
        if any(card.is_leech() for card in note.cards):
            logger.info("Generating image for note: %s", note)
            path = generate_image(note.field2)
            note.set_option("image/path", path)


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


async def send_image_message(
    update: Update,
    context: CallbackContext,
    caption: str,
    image: str = None,
    markup=None,
):
    if update.callback_query is not None:
        # If the session continues, edit photo object.
        message = (
            update.message if update.message else update.callback_query.message
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
        await reply(update, context, "All done for today.", get_finish_image())
        return

    card = cards[0]
    note = card.note

    previous_note = None
    if update.callback_query:
        query = update.callback_query
        logger.info("User query: %s", query)
        if query.data.startswith("grade:"):
            view_id = int(query.data.split(":")[1])
            previous_note = get_view(view_id).card.note

    image_path = None
    note_image_path = note.get_option("image/path")
    if note_image_path and os.path.exists(note_image_path):
        # Note has image: use it.
        image_path = note_image_path
    elif card.is_leech():
        # Note doesn't have image but has leech cards: generate an image.
        try:
            explanation = note.field2
            if not note.language.name == "English":
                explanation = translate(explanation, note.language.name)
                note.set_option("explanation/en", explanation)
            image_path = generate_image(explanation)
            note.set_option("image/path", image_path)
        except:
            logger.warning("Couldn't generate image for note: %s", card.note)
    elif not previous_note or previous_note.get_option("image/path"):
        # Note shouldn't have image but previous one has: set default one.
        image_path = get_default_image()

    keyboard = [
        [InlineKeyboardButton("ANSWER", callback_data=f"answer:{card.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data["current_card_id"] = card.id
    logger.info("Display card front for user %s: %s", user.id, card.front)
    front = format_explanation(card.front)

    await send_image_message(update, context, front, image_path, reply_markup)


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
        # image_path = card.note.get_option("image/path", get_default_image())
        await send_image_message(
            update, context, f"{front}\n\n{back}", None, reply_markup
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
