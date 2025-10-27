import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, List

import fsrs_rs_python as fsrs
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import Integer, ForeignKey, Interval, func


from nachricht import db
from nachricht.db import Model, dttm_utc, log_sql_query
from nachricht.auth import User

from ..config import Config
from ..notes import Note, Language
from .card import Card
from .util import now

logger = logging.getLogger(__name__)


class Answer(Enum):
    """
    Grades in which a user esteems their memory quality on each review.
    The same answer grades are used in FSRS engine.
    """

    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class View(Model):
    __tablename__ = "views"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts_review_started: Mapped[dttm_utc] = mapped_column(
        default=lambda: now(), server_default=func.now()
    )
    ts_review_finished: Mapped[Optional[dttm_utc]] = mapped_column(index=True)
    card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(Card.id), index=True
    )
    review_duration = mapped_column(Interval)
    answer: Mapped[Optional[str]]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ts_review_started": self.ts_review_started,
            "ts_review_finished": self.ts_review_finished,
            "card_id": self.card_id,
            "review_duration": self.review_duration,
            "answer": self.answer,
        }

    def __repr__(self) -> str:
        return (
            f"<View(id={self.id}, "
            f"ts_review_started={self.ts_review_started}, "
            f"ts_review_finished={self.ts_review_finished}, "
            f"card_id={self.card_id}, "
            f"review_duration={self.review_duration}, "
            f"answer={self.answer})>"
        )


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
    view = View(card_id=card_id, ts_review_started=now())
    db.session.add(view)
    db.session.commit()
    logger.info("New view created and transaction committed: %s", view)
    return view.id


def record_answer(
    view_id: int,
    answer: Answer,
) -> None:
    """
    Record an answer for a given view and update card memory state.

    Args:
        view_id: The ID of the view.
        answer: The answer given by the user.
    """
    logger.info(
        "Recording answer for view_id: '%d', answer: '%s'", view_id, answer
    )
    view = get_view(view_id)
    if not view:
        logger.error("Found no view: %s, can't update the card.", view_id)
        return
    card = view.card

    # Save answer and response time.
    view.answer = answer.value
    view.ts_review_finished = now()

    # Update card memory state based on the answer.
    # ... stability and difficulty
    if card.stability and card.difficulty:
        memory = fsrs.MemoryState(card.stability, card.difficulty)
    else:
        memory = None
    # ... days since last update
    if card.ts_last_review:
        interval = (now() - card.ts_last_review).days
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
    card.ts_last_review = now()
    # Due to rounding, "again" grade often results in the immediate review.
    # TODO: prioritize cards which were rescheduled/forgotten
    #       to completely new cards.
    next_interval = round(next_state.interval)
    card.ts_scheduled = now() + timedelta(days=next_interval)
    db.session.commit()
    logger.info(
        "Answer recorded and next review scheduled on %s.",
        card.ts_scheduled.strftime("%Y-%m-%d"),
    )


def count_new_cards_studied(
    user: User, language: Optional[Language] = None, hours_ago: int = 12
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
    time_threshold = now() - timedelta(hours=hours_ago)

    query = (
        db.session.query(Card.id)
        .join(Note)
        .join(View)
        .filter(
            Note.user_id == user.id,
            View.ts_review_finished > time_threshold,
        )
    )

    if language:
        query = query.filter(Note.language_id == language.id)

    log_sql_query(query)

    # Using GROUP BY to achieve distinct behavior in SQLite
    new_cards_studied = query.group_by(Card.id).count()

    return new_cards_studied
