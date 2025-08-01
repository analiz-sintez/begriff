import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, List

import fsrs_rs_python as fsrs
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import (
    Integer,
    ForeignKey,
    Interval,
)


from nachricht import db
from nachricht.db import Model, dttm_utc

from ..config import Config
from ..notes import Note
from .card import Card

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
    ts_review_started: Mapped[dttm_utc]
    ts_review_finished: Mapped[Optional[dttm_utc]]
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey(Card.id))
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
