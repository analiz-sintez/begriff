import logging
from typing import Optional
from sqlalchemy import (
    Integer,
    String,
    ForeignKey,
)
from sqlalchemy.orm import relationship, mapped_column, Mapped

from nachricht.auth import User
from nachricht.db import Model, OptionsMixin
from nachricht.messenger import Context

from .language import Language


logger = logging.getLogger(__name__)


class Note(Model, OptionsMixin):
    __tablename__ = "notes"
    id = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(50))
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": "note",
    }

    field1: Mapped[str]
    field2: Mapped[Optional[str]]
    user_id = mapped_column(Integer, ForeignKey(User.id))
    language_id = mapped_column(Integer, ForeignKey(Language.id))

    cards = relationship(
        "Card", back_populates="note", cascade="all, delete-orphan"
    )
    user = relationship(User, backref="notes")
    language = relationship(Language, backref="notes")

    async def get_display_text(self) -> Optional[str]:
        return self.field2 if self.field2 else ""

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
