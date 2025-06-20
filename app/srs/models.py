from typing import Optional, Annotated
from datetime import datetime
from sqlalchemy import (
    Integer,
    String,
    ForeignKey,
    Interval,
)
from sqlalchemy_utc import UtcDateTime
from sqlalchemy.orm import relationship, mapped_column, Mapped, DeclarativeBase
from enum import Enum
from ..config import Config
from ..core import db, Model, User, OptionsMixin


dttm_utc = Annotated[datetime, mapped_column(UtcDateTime)]


class Language(Model):
    __tablename__ = "languages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}

    def __repr__(self) -> str:
        return f"<Language(id={self.id}, name={self.name})>"


class Note(Model, OptionsMixin):
    __tablename__ = "notes"
    id = mapped_column(Integer, primary_key=True)
    field1: Mapped[str]
    field2: Mapped[str]
    user_id = mapped_column(Integer, ForeignKey(User.id))
    language_id = mapped_column(Integer, ForeignKey(Language.id))

    cards = relationship("Card", backref="note", cascade="all, delete-orphan")
    user = relationship("User", backref="notes")
    language = relationship("Language", backref="notes")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "field1": self.field1,
            "field2": self.field2,
            "user_id": self.user_id,
            "language_id": self.language_id,
        }

    def __repr__(self) -> str:
        return f"<Note(id={self.id}, field1={self.field1}, field2={self.field2}, user_id={self.user_id}, language_id={self.language_id})>"


class Card(Model):
    __tablename__ = "cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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
