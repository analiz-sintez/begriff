import os
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Optional

from nachricht.db import db
from nachricht.auth import User
from nachricht.messenger import Button, Keyboard, Context, Emoji
from nachricht.bus import Signal
from nachricht.i18n import TranslatableString as _

from .. import bus, router
from ..srs import (
    get_cards,
    get_card,
    get_view,
    record_view_start,
    record_answer,
    Answer,
    Maturity,
    count_new_cards_studied,
    DirectCard,
    ReverseCard,
)
from ..llm import translate
from ..config import Config
from ..notes import get_note, Language
from ..srs import ImageCard, CardAdded
from .note import (
    format_explanation,
    ExamplesRequested,
    get_studied_language,
)
from .language import _pack_buttons, StudyLanguageSelected

if Config.IMAGE["enable"]:
    from ..image import generate_image
else:

    async def generate_image(*args, **kwargs):
        return None


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
    note_id: int


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


@router.command("study", description=_("Start a study session"))
@router.authorize()
async def start_study_session(ctx: Context, user: User) -> None:
    logger.info("User %s requested to study.", user.login)
    bus.emit(StudySessionRequested(user.id), ctx=ctx)


def get_remaining_cards(
    ctx: Context, user: User, language: Optional[Language] = None
):
    now = datetime.now(timezone.utc)
    tomorrow = (
        now
        - timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)
        + timedelta(days=1)
    )
    new_cards_remaining = Config.FSRS[
        "new_cards_per_session"
    ] - count_new_cards_studied(user, language, hours_ago=12)
    logger.info("%d new cards remaining.", new_cards_remaining)
    cards = get_cards(
        user_id=user.id,
        language=language,
        end_ts=tomorrow,
        bury_siblings=user.get_option(
            "fsrs/bury_siblings", ctx.config.FSRS["bury_siblings"]
        ),
        randomize=True,
        maturity=(
            None
            if new_cards_remaining > 0
            else [Maturity.YOUNG, Maturity.MATURE]
        ),
    )
    return cards


@dataclass
class NextStudyLanguageSelected(Signal):
    """User finished current language's deck and switched to the next language where planned cards remain."""

    user_id: int
    language_id: int


@bus.on(StudySessionRequested)
@bus.on(CardGraded)
@router.authorize()
# @router.require(frontend=['telegram']) ## TODO: check the frontend type and restrict access from unsupported frontends.
@router.help(
    _(
        "Here you see the question. Try to remember the answer. If you come up with it, press ANSWER to check yourself. If you can't remember it for 10 seconds, don't try too hard, press ANSWER and try to memorize the answer."
    )
)
async def study_next_card(ctx: Context, user: User) -> None:
    """
    Fetch a study card for the user and display it with a button to show
    the answer.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """

    cards = get_remaining_cards(ctx, user, get_studied_language(user))

    if not cards:
        logger.info("User %s has no cards to study.", user.login)
        bus.emit(StudySessionFinished(user.id), ctx=ctx)
        image_path = await get_finish_image()
        # If the user has cards to study in other languages, ask if they want
        # to switch to other languages.
        keyboard = None
        text = "All done for today."
        cards = get_remaining_cards(ctx, user)
        if cards:
            text = "All done for today. Switch to the next language?"
            language_ids = {card.note.language_id for card in cards}
            logger.warning(language_ids)
            languages = [Language.from_id(id) for id in language_ids]
            keyboard = Keyboard(
                _pack_buttons(
                    [
                        Button(
                            language.flag
                            + language.get_localized_name(ctx.locale),
                            NextStudyLanguageSelected(user.id, language.id),
                        )
                        for language in languages
                        if language and language.code
                    ]
                )
            )
        return await ctx.send_message(
            _(text), image=image_path, markup=keyboard
        )

    card = cards[0]

    keyboard = Keyboard([[Button(_("ANSWER"), CardAnswerRequested(card.id))]])
    front = await card.get_front()
    logger.info("Display card front for user %s: %s", user.login, front)
    bus.emit(CardQuestionShown(card.id))
    return await ctx.send_message(
        format_explanation(front["text"]),
        keyboard,
        front.get("image") or (await get_default_image()),
        reply_to=None,
        context={"note_id": card.note.id, "card_id": card.id},
        on_reaction=(
            {
                Emoji.PRAY: (
                    ExamplesRequested(note_id=card.note.id)
                    if isinstance(card, DirectCard)
                    else []
                ),
            }
        ),
    )


@bus.on(NextStudyLanguageSelected)
@router.authorize()
async def switch_language_and_continue_studying(
    ctx: Context, language_id: int
):
    if not (language := Language.from_id(language_id)):
        return
    await bus.emit_and_wait(
        StudyLanguageSelected(ctx.user.id, language.code), ctx=ctx
    )
    bus.emit(StudySessionRequested(ctx.user.id), ctx=ctx)


@bus.on(CardAnswerRequested)
@router.authorize()
@router.help(
    _(
        "Here you rate your memorization. If you couldn't come up with an answer, or your answer is wrong, press AGAIN, and the card will show up soon again. If your answer is correct, press GOOD, and the card will be scheduled for tomorrow or later."
    )
)
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
    back = await card.get_back()
    back["text"] = format_explanation(back["text"])

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
                Button(_(answer.name), CardGradeSelected(view_id, answer))
                for answer in Answer
            ]
        ]
    )
    return await ctx.send_message(
        back["text"],
        keyboard,
        back.get("image"),
        on_reaction={
            Emoji.PRAY: ExamplesRequested(note_id=note.id),
        },
    )


@bus.on(CardGradeSelected)
@router.authorize()
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


@dataclass
class MissingImageCardFound(Signal):
    note_id: int


@bus.on(CardGraded)
async def maybe_generate_image(view_id: int):
    if not (view := get_view(view_id)):
        return

    card = view.card
    note = card.note

    # Don't generate new image if an old one is in place.
    image_path = note.get_option("image/path")
    if image_path and os.path.exists(image_path):
        # ...but create an image card if none exists
        logger.info("Creating missing image card for note %s", note.id)
        if not any([isinstance(c, ImageCard) for c in note.cards]):
            bus.emit(MissingImageCardFound(note.id))
        return

    # Generate images only for leech cards
    if not card.is_leech():
        return

    # Translate any language to English since models understand it.
    option_key = "explanations/en"
    if note.language.name == "English":
        explanation = note.field2
    elif not (explanation := note.get_option(option_key)):
        explanation = await translate(note.field2, note.language.name)
        note.set_option(option_key, explanation)

    # Generate an image.
    try:
        image_path = await generate_image(explanation)
        note.set_option("image/path", image_path)
        bus.emit(ImageGenerated(note.id))
    except Exception as e:
        logger.warning(
            "Couldn't generate image for note: %s. Error: %s", note, e
        )


@bus.on(ImageGenerated)
@bus.on(MissingImageCardFound)
async def add_image_card(note_id: int):
    if not (note := get_note(note_id)):
        return
    logger.info("Creating an image card for note %s", note.id)
    now = datetime.now(timezone.utc)
    card = ImageCard(note_id=note.id, ts_scheduled=now)
    db.session.add(card)
    db.session.commit()
    bus.emit(CardAdded(card.id))
    return card
