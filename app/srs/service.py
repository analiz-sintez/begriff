import random
import logging
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Union
from datetime import datetime, timedelta, timezone

import fsrs_rs_python as fsrs
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_
from sqlalchemy.orm import aliased

from ..config import Config
from ..core import db
from ..bus import Signal, bus
from .models import Note, Card, View, Language, Answer


# TODO: Move this one into `srs.service`?
@dataclass
class CardAdded(Signal):
    card_id: int


logger = logging.getLogger(__name__)


def log_sql_query(query) -> None:
    """
    Log the SQL query statement if available.

    Args:
        query: SQLAlchemy query object.
    """
    if query is not None:
        query_text = str(
            query.statement.compile(compile_kwargs={"literal_binds": True})
        )
        logger.debug("SQL Query: %s", query_text)


def get_language(identifier: Optional[Union[str, int]] = None) -> Language:
    """
    Retrieve or create a language by name or id. The provided identifier
    is considered as a name if it's a string, or an id if it's an integer.

    Args:
        identifier: The name or id of the language.

    Returns:
        Language: The language object.
    """
    if isinstance(identifier, str):
        logger.info("Retrieving language with name: %s", identifier)
        language = Language.query.filter_by(name=identifier).first()
    elif isinstance(identifier, int):
        logger.info("Retrieving language with id: %d", identifier)
        language = Language.query.filter_by(id=identifier).first()
    else:
        raise ValueError("Identifier must be a string (name) or integer (id).")

    if not language and isinstance(identifier, str):
        logger.info("Language not found, creating new one: %s", identifier)
        language = Language(name=identifier)

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
) -> Note:
    """
    Add a note for studying: create cards and schedule them.

    Args:
        text: The word or phrase to add.
        explanation: Explanation of the text.
        language_id: ID of the language.
        user_id: ID of the user.

    Returns:
        Note: The note object created.
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
        bus.emit(CardAdded(front_card.id))
        bus.emit(CardAdded(back_card.id))
        logger.info(
            "Transaction committed successfully for word note creation."
        )
        return note
    except IntegrityError as e:
        db.session.rollback()
        logger.error("Integrity error occurred: %s", e)
        raise e


def update_note(note: Note) -> None:
    """
    Update the given note.

    Args:
        note: The note to update.
    """
    logger.info("Updating note with id: %d", note.id)
    cards = Card.query.filter_by(note_id=note.id).all()
    for card in cards:
        if card.front == note.field1:
            card.back = note.field2
            logger.info("Card updated: %s", card)
        elif card.back == note.field1:
            card.front = note.field2
            logger.info("Card updated: %s", card)
    db.session.commit()
    logger.info("Note update committed successfully.")


def get_view(view_id: int) -> Optional[View]:
    """
    Get a view by id.

    Args:
        view_id: The id of the view.

    Returns:
        View: The view object, or None if not found.
    """
    logger.info("Getting view by id '%d'", view_id)
    return View.query.filter_by(id=view_id).first()


def get_views(
    user_id: int,
    language_id: int,
    answers: Optional[List[Answer]] = None,
) -> List[View]:
    """
    Retrieve views for a specific user and language. Allows optional filtering by answers.

    Args:
        user_id: The ID of the user.
        language_id: The ID of the language.
        answers: Optional list of answers to filter views by.

    Returns:
        List[View]: A list of View objects matching the filter criteria.
    """
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

    Args:
        card_id: ID of the card for which view is being created.

    Returns:
        int: The ID of the created view.
    """
    logger.info("Creating new view for card_id: %d", card_id)
    view = View(card_id=card_id, ts_review_started=datetime.now(timezone.utc))
    db.session.add(view)
    db.session.commit()
    logger.info("New view created and transaction committed: %s", view)
    return view.id


def record_answer(view_id: int, answer: Answer) -> None:
    """
    Record an answer for a given view and update card memory state.

    Args:
        view_id: The ID of the view.
        answer: The answer given by the user.
    """
    logger.info(
        "Recording answer for view_id: '%d', answer: '%s'", view_id, answer
    )
    view = db.session.query(View).filter_by(id=view_id).first()
    if not view:
        logger.error("Found no view: %s, can't update the card.", view_id)
        return
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
    next_state = getattr(next_states, answer.value)

    logger.info(
        "Card memory parameters updated for card_id '%d'. "
        "Stability: %.1f -> %.1f, Difficulty: %.1f -> %.1f",
        card.id,
        card.stability if card.stability else 0.0,
        next_state.memory.stability,
        card.difficulty if card.difficulty else 0.0,
        next_state.memory.difficulty,
    )

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
        "Answer recorded and next review scheduled on %s.",
        card.ts_scheduled.strftime("%Y-%m-%d"),
    )


def get_note(note_id: int) -> Optional[Note]:
    """
    Get a note by id.

    Args:
        note_id: The id of the note.

    Returns:
        Note: The note object, or None if not found.
    """
    logger.info("Getting note by id '%d'", note_id)
    return Note.query.filter_by(id=note_id).first()


def get_card(card_id: int) -> Optional[Card]:
    """
    Get a card by id.

    Args:
        card_id: The id of the card.

    Returns:
        Card: The card object, or None if not found.
    """
    logger.info("Getting card by id '%d'", card_id)
    return Card.query.filter_by(id=card_id).first()


class Maturity(Enum):
    NEW = "new"
    YOUNG = "young"
    MATURE = "mature"


def get_notes(
    user_id: int,
    language_id: Optional[int] = None,
    text: Optional[str] = None,
    explanation: Optional[str] = None,
    maturity: Optional[List[Maturity]] = None,
    order_by: Optional[str] = None,
) -> List[Note]:
    """
    Retrieve notes for a specific user and language. Allows optional filtering by text, explanation, and maturity, with optional sorting.

    Args:
        user_id: The ID of the user.
        language_id: The ID of the language.
        text: Optional text to filter notes by.
        explanation: Optional explanation to filter notes by.
        maturity: Optional list of maturity levels to filter notes by.
        order_by: Optional field to sort results by ('field1' or 'field2').

    Returns:
        List[Note]: A list of Note objects matching the filter criteria.
    """
    logger.info(
        "Getting notes for user_id: '%s', language_id: '%s', text: '%s', explanation: '%s', maturity: '%s', order_by: '%s'",
        user_id,
        language_id,
        text,
        explanation,
        maturity,
        order_by,
    )
    query = db.session.query(Note).filter_by(user_id=user_id)

    if language_id:
        query = query.filter_by(language_id=language_id)

    if text:
        if text.startswith("=~"):
            logger.debug("Applying regex filter on text: '%s'", text[2:])
            query = query.filter(Note.field1.op("REGEXP")(text[2:]))
        elif "%" in text or "_" in text:
            logger.debug("Applying SQL LIKE filter on text: '%s'", text)
            query = query.filter(Note.field1.like(text))
        else:
            logger.debug("Applying exact match filter on text: '%s'", text)
            query = query.filter(Note.field1 == text)

    if explanation:
        if explanation.startswith("=~"):
            logger.debug(
                "Applying regex filter on explanation: '%s'", explanation[2:]
            )
            query = query.filter(Note.field2.op("REGEXP")(explanation[2:]))
        elif "%" in explanation or "_" in explanation:
            logger.debug(
                "Applying SQL LIKE filter on explanation: '%s'", explanation
            )
            query = query.filter(Note.field2.like(explanation))
        else:
            logger.debug(
                "Applying exact match filter on explanation: '%s'", explanation
            )
            query = query.filter(Note.field2 == explanation)

    if maturity:
        CardAlias = aliased(Card)
        conditions = []
        # This is incorrect since it depends on the current date.
        # Definition of maturity shouldn't depend on it.
        # But maybe for the injection menas it is good.
        timetable_mature = datetime.now(timezone.utc) + timedelta(
            days=Config.FSRS["mature_threshold"]
        )
        for m in maturity:
            if m == Maturity.NEW:
                subquery = (
                    db.session.query(CardAlias.note_id.distinct())
                    .filter(~CardAlias.ts_last_review.is_(None))
                    .cte("new_notes")
                )
                conditions.append(~Note.id.in_(subquery.select()))
            elif m == Maturity.YOUNG:
                subquery = (
                    db.session.query(CardAlias.note_id.distinct())
                    .filter(
                        and_(
                            CardAlias.ts_last_review.isnot(None),
                            CardAlias.ts_scheduled <= timetable_mature,
                        )
                    )
                    .cte("young_notes")
                )
                conditions.append(Note.id.in_(subquery.select()))
            elif m == Maturity.MATURE:
                subquery = (
                    db.session.query(CardAlias.note_id.distinct())
                    .filter(
                        ~and_(
                            CardAlias.ts_last_review.isnot(None),
                            CardAlias.ts_scheduled > timetable_mature,
                        )
                    )
                    .cte("mature_notes")
                )
                conditions.append(~Note.id.in_(subquery.select()))

        query = query.filter(db.or_(*conditions))

    if order_by in ["field1", "field2"]:
        query = query.order_by(getattr(Note, order_by))

    log_sql_query(query)
    results = query.all()
    logger.info("Retrieved %i notes", len(results))
    logger.debug("\n".join([str(note) for note in results]))
    return results


def count_new_cards_studied(
    user_id: int, language_id: int, hours_ago: int
) -> int:
    """
    Calculate how many cards were studied for the first time during the last
    specified hours.

    A card is studied the first time if it has views with answers, and the earliest
    such view was within the past specified hours.

    Args:
        user_id: The ID of the user.
        language_id: The ID of the language.
        hours_ago: The number of hours to look back.

    Returns:
        The number of cards studied for the first time in the last specified hours.
    """
    time_threshold = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    cards = (
        Card.query.join(Note)
        .filter(Note.user_id == user_id, Note.language_id == language_id)
        .all()
    )
    new_cards_studied = 0

    for card in cards:
        views_with_answers = [view for view in card.views if view.answer]
        if views_with_answers:
            earliest_view = min(
                view.ts_review_started for view in views_with_answers
            )
            if earliest_view > time_threshold:
                new_cards_studied += 1

    return new_cards_studied


def get_cards(
    user_id: int,
    language_id: Optional[int] = None,
    start_ts: Optional[datetime] = None,
    end_ts: Optional[datetime] = None,
    bury_siblings: bool = False,
    maturity: Optional[List[Maturity]] = None,
    randomize: bool = False,
) -> List[Card]:
    """
    Retrieve cards for a specific user and language. Allows optional filtering by language, time, and other criteria.

    Args:
        user_id: The ID of the user.
        language_id: Optional ID of the language.
        start_ts: Optional start timestamp to filter cards by.
        end_ts: Optional end timestamp to filter cards by.
        bury_siblings: Optional flag to exclude sibling cards.
        randomize: Optional flag to randomize the order of the cards.

    Returns:
        List[Card]: A list of Card objects matching the filter criteria.
    """
    logger.info(
        "Getting cards for user_id: '%d', language_id: '%d', "
        "start_ts: '%s', end_ts: '%s', bury_siblings: '%s', randomize: '%s'",
        user_id,
        language_id,
        start_ts,
        end_ts,
        bury_siblings,
        randomize,
    )
    query = db.session.query(Card).join(Note)
    query = query.filter(Note.user_id == user_id)

    if language_id:
        query = query.filter(Note.language_id == language_id)

    if start_ts:
        query = query.filter(Card.ts_scheduled > start_ts)

    if end_ts:
        query = query.filter(Card.ts_scheduled <= end_ts)

    if bury_siblings:
        # If a note has a card reviewed today, don't include its sibling cards,
        # only allow to review the reviewed card again.
        # ...step 1: Find all cards that were reviewed today
        recently_viewed_cards = (
            db.session.query(View.card_id.distinct().label("card_id"))
            .filter(
                View.ts_review_finished
                > (datetime.now(timezone.utc) - timedelta(hours=12))
            )
            .cte("recently_viewed_cards")
            .select()
        )
        # ...step 2: Find distinct note_ids associated with these cards
        recent_notes = (
            db.session.query(Card.note_id.distinct().label("note_id"))
            .filter(Card.id.in_(recently_viewed_cards))
            .cte("recent_notes")
            .select()
        )
        # ...step 3: Allow only those cards which belong to notes found in step 2
        #    For other notes, allow all cards
        query = query.filter(
            db.or_(
                ~Card.note_id.in_(recent_notes),
                Card.note_id.in_(recently_viewed_cards)
                & Card.id.in_(recently_viewed_cards),
            )
        )

    if maturity:
        conditions = []
        timetable_mature = datetime.now(timezone.utc) + timedelta(
            days=Config.FSRS["mature_threshold"]
        )
        for m in maturity:
            if m == Maturity.NEW:
                conditions.append(Card.ts_last_review.is_(None))
            elif m == Maturity.YOUNG:
                conditions.append(
                    and_(
                        Card.ts_last_review.isnot(None),
                        Card.ts_scheduled <= timetable_mature,
                    )
                )
            elif m == Maturity.MATURE:
                conditions.append(
                    and_(
                        Card.ts_last_review.isnot(None),
                        Card.ts_scheduled > timetable_mature,
                    )
                )

        query = query.filter(db.or_(*conditions))

    if not randomize:
        query = query.order_by(Card.ts_scheduled.asc())

    log_sql_query(query)
    results = query.all()
    if randomize:
        random.shuffle(results)

    logger.info("Retrieved %i cards", len(results))
    logger.debug("\n".join([str(card) for card in results]))
    return results
