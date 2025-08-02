from enum import Enum
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import relationship, mapped_column, Mapped
from sqlalchemy import Integer, String, ForeignKey, func

from nachricht.db import Model, OptionsMixin, dttm_utc
from nachricht.bus import Signal

from ..config import Config
from ..notes import Note


logger = logging.getLogger(__name__)


class Maturity(Enum):
    NEW = "new"
    YOUNG = "young"
    MATURE = "mature"


@dataclass
class CardAdded(Signal):
    card_id: int


class Card(Model, OptionsMixin):
    __tablename__ = "cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts_created: Mapped[dttm_utc] = mapped_column(
        default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    type: Mapped[str] = mapped_column(String(50))
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": "card",
    }

    note_id: Mapped[int] = mapped_column(Integer, ForeignKey(Note.id))
    note = relationship("Note", back_populates="cards")

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

    @property
    def front(self):
        raise NotImplementedError()

    @property
    def back(self):
        raise NotImplementedError()


class DirectCard(Card):
    __mapper_args__ = {
        "polymorphic_identity": "direct_card",
    }

    @property
    def front(self):
        return self.note.field1

    @property
    def back(self):
        return self.note.field2


class ReverseCard(Card):
    __mapper_args__ = {
        "polymorphic_identity": "reverse_card",
    }

    @property
    def front(self):
        return self.note.field2

    @property
    def back(self):
        return self.note.field1


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
