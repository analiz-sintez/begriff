import os
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from ..auth import User
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
)
from ..llm import translate
from ..image import generate_image
from ..config import Config
from .note import format_explanation, get_explanation_in_native_language
from ..messenger import authorize, Button, Keyboard, Context, router
from ..bus import Signal, bus


# States: ASK -> ANSWER -> RECORD
# - ASK: show the front side of the card, wait when user requests
#   the back side;
# - ANSWER: show front and back sides, wait for grade (Answer object);
# - GRADE: got the answer, record it, update card memorization params
#   and reschedule it.


@dataclass
class StudySessionRequested(Signal):
    user_id: int


@dataclass
class CardQuestionShown(Signal):
    card_id: int


@dataclass
class CardAnswerRequested(Signal):
    card_id: int


@dataclass
class CardAnswerShown(Signal):
    card_id: int


@dataclass
class CardGradeSelected(Signal):
    view_id: int
    answer: Answer


@dataclass
class CardGraded(Signal):
    view_id: int
    answer: Answer


@dataclass
class StudySessionFinished(Signal):
    user_id: int


@dataclass
class ImageGenerated(Signal):
    view_id: int


logger = logging.getLogger(__name__)


async def get_default_image():
    image_path = await generate_image("Stars in the deep night sky.")
    return image_path


async def get_finish_image():
    image_path = await generate_image(
        "A cat teacher in round glasses and his young"
        " cat students celebrate the end of the lection."
    )
    return image_path


async def _get_image_for_show(card, previous_card=None):
    note = card.note
    image_path = note.get_option("image/path")
    # Note has image: use it.
    if image_path and os.path.exists(image_path):
        return image_path
    # Note shouldn't have image but previous one has: set default one.
    if not previous_card or previous_card.note.get_option("image/path"):
        return await get_default_image()


@router.command("study", description="Start a study session")
@authorize()
async def start_study_session(ctx: Context, user: User) -> None:
    logger.info("User %s requested to study.", user.login)
    bus.emit(StudySessionRequested(user.id), ctx=ctx)


@bus.on(StudySessionRequested)
@bus.on(CardGraded)
@authorize()
async def study_next_card(ctx: Context, user: User) -> None:
    """
    Fetch a study card for the user and display it with a button to show
    the answer.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """

    language = get_language(
        user.get_option(
            "studied_language", Config.LANGUAGE["defaults"]["study"]
        )
    )

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
        bus.emit(StudySessionFinished(user.id))
        image_path = await get_finish_image()
        return await ctx.send_message("All done for today.", image=image_path)

    card = cards[0]
    image_path = await _get_image_for_show(card)

    keyboard = Keyboard([[Button("ANSWER", CardAnswerRequested(card.id))]])
    logger.info("Display card front for user %s: %s", user.login, card.front)
    front = card.front
    # If the card is reversed (explanation -> word), translate the explanation.
    note = card.note
    if front == note.field2:
        front = await get_explanation_in_native_language(note)
    front = format_explanation(front)
    bus.emit(CardQuestionShown(card.id))
    await ctx.send_message(front, keyboard, image_path)


@bus.on(CardAnswerRequested)
@authorize()
async def handle_study_answer(ctx: Context, user: User, card_id: int) -> None:
    """
    Handle ANSWER button press and show grade buttons.
    """
    logger.info("User %s pressed a button: ANSWER", user.login)

    # ASK -> ANSWER:
    # Show the answer (showing back side of the card)
    if not (card := get_card(card_id)):
        return
    note = card.note
    # ... translate the explanation
    # ... if it is on the front
    front = card.front
    if front == note.field2:
        front = await get_explanation_in_native_language(note)
    front = format_explanation(front)
    # ... if it is on the back
    back = card.back
    if back == note.field2:
        back = await get_explanation_in_native_language(note)
    back = format_explanation(back)

    bus.emit(CardAnswerShown(card.id))
    logger.info(
        "Showing answer for card %s to user %s: %s",
        card.id,
        user.login,
        back,
    )
    # ... record the moment user started answering
    view_id = record_view_start(card.id)
    # ... prepare the keyboard with memorization quality buttons

    keyboard = Keyboard(
        [
            [
                Button(answer.name, CardGradeSelected(view_id, answer))
                for answer in Answer
            ]
        ]
    )
    await ctx.send_message(f"{front}\n\n{back}", keyboard)


@bus.on(CardGradeSelected)
@authorize()
async def handle_study_grade(
    ctx: Context,
    user: User,
    view_id: int,
    answer: Answer,
) -> None:
    """
    Handle grade buttons press (AGAIN ... EASY) from user to and record
    the answer.
    """
    if not (view := get_view(view_id)):
        return
    logger.info("User %s pressed a button: %s", user.login, answer)
    # ANSWER -> GRADE
    logger.info(
        "User %s graded answer %s for view %s",
        user.login,
        answer.name,
        view.id,
    )
    record_answer(view.id, answer)
    bus.emit(CardGraded(view.id, answer), ctx=ctx)


@bus.on(CardGraded)
async def maybe_generate_image(view_id: int):
    if not (view := get_view(view_id)):
        return

    card = view.card

    # Generate images only for leech cards
    if not card.is_leech():
        return

    note = card.note

    # Don't generate new image if an old one is in place.
    image_path = note.get_option("image/path")
    if image_path and os.path.exists(image_path):
        return

    # Translate any language to English since models understand it.
    explanation = note.field2
    if not note.language.name == "English":
        explanation = await translate(explanation, note.language.name)
        note.set_option("explanation/en", explanation)

    # Generate an image.
    try:
        image_path = await generate_image(explanation)
        note.set_option("image/path", image_path)
        bus.emit(ImageGenerated(view_id))
    except:
        logger.warning("Couldn't generate image for note: %s", note)
