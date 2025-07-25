from enum import Enum
from typing import Optional, Dict
from sqlalchemy import (
    Integer,
    String,
    ForeignKey,
    Interval,
)
from babel import Locale
from babel.localedata import locale_identifiers

from sqlalchemy.orm import relationship, mapped_column, Mapped

from core.db import Model, OptionsMixin, dttm_utc
from core.auth import User
from ..config import Config
from ..notes import Note, Language


class Card(Model, OptionsMixin):
    __tablename__ = "cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(50))
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": "card",
    }

    note_id: Mapped[int] = mapped_column(Integer, ForeignKey(Note.id))
    front: Mapped[str]
    back: Mapped[str]

    # Memory state:
    # those two we don't know before the first review
    stability: Mapped[Optional[float]]
    difficulty: Mapped[Optional[float]]

    # required to calculate interval from the last review
    # when updating memory state.
    ts_last_review: Mapped[Optional[dttm_utc]]
    # is used to fetch cards for today's review
    ts_scheduled: Mapped[dttm_utc]

    views = relationship("View", backref="card", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "note_id": self.note_id,
            "front": self.front,
            "back": self.back,
            "stability": self.stability,
            "difficulty": self.difficulty,
            "ts_scheduled": self.ts_scheduled,
        }

    def __repr__(self) -> str:
        return (
            f"<Card(id={self.id}, "
            f"note_id={self.note_id}, "
            f"stability={self.stability}, "
            f"difficulty={self.difficulty}, "
            f"front={self.front}, back={self.back}, "
            f"ts_scheduled={self.ts_scheduled})>"
        )

    def is_leech(self) -> bool:
        return (
            self.difficulty is not None
            and self.difficulty >= Config.FSRS["card_is_leech"]["difficulty"]
            and len(self.views) >= Config.FSRS["card_is_leech"]["view_cnt"]
        )


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
