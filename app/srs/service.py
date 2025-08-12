import re
import time
import random
import logging
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_
from sqlalchemy.orm import aliased

from nachricht import db
from nachricht.db import log_sql_query
from nachricht.auth import User

from .. import bus
from ..config import Config
from ..notes import Note, Language, WordNote
from .view import View
from .card import Card, Maturity, DirectCard, ReverseCard, CardAdded


logger = logging.getLogger(__name__)


def get_cards(
    user_id: int,
    language: Optional[Language] = None,
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
        "Getting cards for user_id: '%d', language: '%s', "
        "start_ts: '%s', end_ts: '%s', bury_siblings: '%s', randomize: '%s'",
        user_id,
        language,
        start_ts,
        end_ts,
        bury_siblings,
        randomize,
    )
    query = db.session.query(Card).join(Note)
    query = query.filter(Note.user_id == user_id)

    if language:
        query = query.filter(Note.language_id == language.id)

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
        note = WordNote(
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
        front_card = DirectCard(note_id=note.id, ts_scheduled=now)
        back_card = ReverseCard(note_id=note.id, ts_scheduled=now)
        db.session.add_all([front_card, back_card])
        db.session.flush()
        logger.info("Cards created: %s, %s", front_card, back_card)

        db.session.commit()
        bus.emit(CardAdded(front_card.id))
        bus.emit(CardAdded(back_card.id))
        logger.debug(
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
    logger.info("Note update with id: %d skipped.", note.id)


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


def format_explanation(text: Optional[str]) -> str:
    """Format an explanation: add newline before brackets, remove them, use /.../, and lowercase the insides of the brackets.

    Args:
        explanation: The explanation string to format.

    Returns:
        The formatted explanation string.
    """
    if text is None:
        return ""
    return re.sub(
        r"\[([^\]]+)\]",
        lambda match: f"\n_{match.group(1).lower()}_",
        text,
    )


_notes_to_inject_cache = {}
_cache_time = {}


def get_notes_to_inject(user: User, language: Language) -> list:
    """Retrieve notes to inject for a specific user and language, filtering by maturity and returning a random subset.

    Args:
        user: The user object.
        language: The language object.

    Returns:
        A list of notes for the given user and language, filtered and randomized.
    """
    current_time = time.time()
    cache_key = (user.id, language.id)

    # Invalidate cache if older than 1 minute
    if cache_key in _cache_time and current_time - _cache_time[cache_key] > 60:
        del _notes_to_inject_cache[cache_key]
        del _cache_time[cache_key]

    if cache_key not in _notes_to_inject_cache:
        # Fetch only notes of specified maturity
        notes = get_notes(
            user.id,
            language.id,
            maturity=[
                getattr(Maturity, m.upper())
                for m in Config.LLM["inject_maturity"]
            ],
        )
        # Randomly select inject_count notes
        _notes_to_inject_cache[cache_key] = notes
        _cache_time[cache_key] = current_time

    notes = _notes_to_inject_cache[cache_key]
    random_notes = random.sample(
        notes, min(Config.LLM["inject_count"], len(notes))
    )
    return random_notes
