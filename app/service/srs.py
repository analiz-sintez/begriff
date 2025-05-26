import random
import logging
import fsrs_rs_python as fsrs
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from ..models import db, Note, Card, View, Language, Answer
from ..config import Config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_language(name):
    logger.info("Retrieving language with name: %s", name)
    language = Language.query.filter_by(name=name).first()
    if not language:
        logger.info("Language not found, creating new language: %s", name)
        language = Language(name=name)
        try:
            db.session.add(language)
            db.session.commit()
            logger.info("Language created successfully: %s", language)
        except IntegrityError as e:
            db.session.rollback()
            logger.error(
                "Integrity error occurred while creating a language: %s", e
            )
            raise ValueError(
                "Integrity error occurred while creating a language."
            )
    return language


def create_word_note(
    text: str, explanation: str, language_id: int, user_id: int
):
    """
    Add a note for studying: create cards and schedule them.
    """
    logger.info(
        "Creating word note with text: '%s', explanation: '%s', "
        "language_id: '%d', user_id: '%d'",
        text,
        explanation,
        language_id,
        user_id,
    )
    if not text:
        logger.error("Word or phrase cannot be empty.")
        raise ValueError("Word or phrase cannot be empty.")
    if not user_id or not language_id:
        logger.error("User ID and Language ID must be provided.")
        raise ValueError("User ID and Language ID must be provided.")

    try:
        # Create a note.
        note = Note(
            field1=text,
            field2=explanation,
            user_id=user_id,
            language_id=language_id,
        )
        db.session.add(note)
        db.session.flush()
        logger.info("Note created: %s", note)

        # Create two cards for the note.
        now = datetime.now(timezone.utc)
        front_card = Card(
            note_id=note.id, front=text, back=explanation, ts_scheduled=now
        )
        back_card = Card(
            note_id=note.id, front=explanation, back=text, ts_scheduled=now
        )
        db.session.add_all([front_card, back_card])
        logger.info("Cards created: %s, %s", front_card, back_card)

        db.session.commit()
        logger.info(
            "Transaction committed successfully for word note creation."
        )
    except IntegrityError as e:
        db.session.rollback()
        logger.error("Integrity error occurred: %s", e)
        raise e


def get_view(view_id: int):
    logger.info("Getting view by id '%d'", view_id)
    return View.query.filter_by(id=view_id).first()


def get_views(
    user_id: int,
    language_id: int,
    answers: list = None,
):
    logger.info(
        "Getting views for user_id: '%d', language_id: '%d', answers: '%s'",
        user_id,
        language_id,
        answers,
    )
    query = db.session.query(View).join(Card).join(Note)
    query = query.filter(Note.user_id == user_id)
    query = query.filter(Note.language_id == language_id)

    if answers:
        conditions = []
        values_to_check = [
            answer.value for answer in answers if answer is not None
        ]
        if None in answers:
            conditions.append(View.answer.is_(None))
        if values_to_check:
            conditions.append(View.answer.in_(values_to_check))
        if conditions:
            query = query.filter(db.or_(*conditions))

    results = query.all()
    logger.info("Retrieved %i views", len(results))
    logger.debug("\n".join([str(view) for view in results]))
    return results


def record_view_start(card_id: int) -> int:
    """
    Create a view and save the time it started.
    """
    logger.info("Creating new view for card_id: '%d'", card_id)
    view = View(card_id=card_id, ts_review_started=datetime.now(timezone.utc))
    db.session.add(view)
    db.session.commit()
    logger.info("New view created and transaction committed: %s", view)
    return view.id


def record_answer(view_id: int, answer: Answer):
    logger.info(
        "Recording answer for view_id: '%d', answer: '%s'", view_id, answer
    )
    view = db.session.query(View).filter_by(id=view_id).first()
    if not view:
        logger.error("Found no view: %s, can't update the card.", view_id)
        return None
    card = Card.query.filter_by(id=view.card_id).first()

    # Save answer and response time.
    view.answer = answer.value
    view.ts_review_finished = datetime.now(timezone.utc)

    # Update card memory state based on the answer.
    # ... stability and difficulty
    if card.stability and card.difficulty:
        memory = fsrs.MemoryState(card.stability, card.difficulty)
    else:
        memory = None
    # ... days since last update
    if card.ts_last_review:
        interval = (datetime.now(timezone.utc) - card.ts_last_review).days
    else:
        interval = 0
    # IDEA: use personal parameters, reevaluate them after every 1000 views.
    planner = fsrs.FSRS(parameters=fsrs.DEFAULT_PARAMETERS)
    next_states = planner.next_states(
        memory, Config.FSRS["target_retention"], interval
    )
    next_state = getattr(next_states, str(answer))
    card.stability = next_state.memory.stability
    card.difficulty = next_state.memory.difficulty

    # Reschedule the card.
    card.ts_last_review = datetime.now(timezone.utc)
    # Due to rounding, "again" grade often results in the immediate review.
    # TODO: prioritize cards which were rescheduled/forgotten
    #       to completely new cards.
    next_interval = round(next_state.interval)
    card.ts_scheduled = datetime.now(timezone.utc) + timedelta(
        days=next_interval
    )
    db.session.commit()
    logger.info(
        "Answer recorded and next review scheduled in %i days.", next_interval
    )


def get_card(card_id: int):
    logger.info("Getting card by id '%d'", card_id)
    return Card.query.filter_by(id=card_id).first()


def get_cards(
    user_id: int,
    language_id: int,
    start_ts: datetime = None,
    end_ts: datetime = None,
    bury_siblings: bool = False,
    randomize: bool = False,
):
    logger.info(
        "Getting cards for user_id: '%d', language_id: '%d', start_ts: '%s', end_ts: '%s', bury_siblings: '%s', randomize: '%s'",
        user_id,
        language_id,
        start_ts,
        end_ts,
        bury_siblings,
        randomize,
    )
    query = db.session.query(Card).join(Note)
    query = query.filter(Note.user_id == user_id)
    query = query.filter(Note.language_id == language_id)

    if start_ts:
        query = query.filter(Card.ts_scheduled > start_ts)

    if end_ts:
        query = query.filter(Card.ts_scheduled <= end_ts)

    if bury_siblings:
        recent_views_subquery = (
            db.session.query(View.card_id)
            .join(Card)
            .filter(
                View.ts_review_finished
                > (datetime.utcnow() - timedelta(hours=12))
            )
            .subquery()
        )
        query = query.filter(~Card.id.in_(recent_views_subquery))

    if not randomize:
        query = query.order_by(Card.ts_scheduled.asc())

    results = query.all()
    if randomize:
        random.shuffle(results)

    logger.info("Retrieved %i cards", len(results))
    logger.debug("\n".join([str(card) for card in results]))
    return results
