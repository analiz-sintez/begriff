from enum import Enum
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal, Dict

from sqlalchemy.orm import relationship, mapped_column, Mapped
from sqlalchemy import Integer, String, ForeignKey, func

from nachricht.db import Model, OptionsMixin, dttm_utc
from nachricht.auth import User
from nachricht.bus import Signal

from ..config import Config
from ..notes import Note, Language


logger = logging.getLogger(__name__)


class Maturity(Enum):
    NEW = "new"
    YOUNG = "young"
    MATURE = "mature"


@dataclass
class CardAdded(Signal):
    card_id: int


OutputKey = Literal["text", "image"]
OutputDict = Dict[OutputKey, Optional[str]]


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
            f"ts_scheduled={self.ts_scheduled})>"
        )

    def is_leech(self) -> bool:
        return (
            self.difficulty is not None
            and self.difficulty >= Config.FSRS["card_is_leech"]["difficulty"]
            and len(self.views) >= Config.FSRS["card_is_leech"]["view_cnt"]
        )

    async def get_front(self) -> OutputDict:
        raise NotImplementedError()

    async def get_back(self) -> OutputDict:
        raise NotImplementedError()


class DirectCard(Card):
    __mapper_args__ = {
        "polymorphic_identity": "direct_card",
    }

    async def get_front(self) -> OutputDict:
        """Show only text, not the image."""
        return {"text": self.note.field1}

    async def get_back(self) -> OutputDict:
        """Show both the text and the image."""
        # if the image presents, show it, of not — don't
        front = await self.get_front()
        front["text"] = (
            front["text"] + "\n\n" + (await self.note.get_display_text())
        )
        front["image"] = await self.note.get_image()
        return front


class ReverseCard(Card):
    __mapper_args__ = {
        "polymorphic_identity": "reverse_card",
    }

    async def get_front(self) -> OutputDict:
        return {
            "text": await self.note.get_display_text(),
            "image": await self.note.get_image(),
        }

    async def get_back(self) -> OutputDict:
        front = await self.get_front()
        front["text"] = front["text"] + "\n\n" + self.note.field1
        return front


class ImageCard(Card):
    """Show image, guess the word and the explanation."""

    __mapper_args__ = {
        "polymorphic_identity": "image_card",
    }

    async def get_front(self) -> OutputDict:
        if not (image_path := await self.note.get_image()):
            raise RuntimeError("Image card required but no image found.")

        return {"text": None, "image": image_path}

    async def get_back(self) -> OutputDict:
        front = await self.get_front()
        front["text"] = (
            self.note.field1 + "\n\n" + (await self.note.get_display_text())
        )

        return front


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
    time_threshold = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    query = Card.query.join(Note).filter(Note.user_id == user.id)
    if language:
        query = query.filter(Note.language_id == language.id)
    cards = query.all()
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
