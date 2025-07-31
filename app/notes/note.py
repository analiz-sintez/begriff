import logging
from typing import Optional, Dict, Union
from sqlalchemy import (
    Integer,
    String,
    ForeignKey,
)
from babel import Locale
from babel.localedata import locale_identifiers

from sqlalchemy.orm import relationship, mapped_column, Mapped
from sqlalchemy.exc import IntegrityError

from nachricht.auth import User
from nachricht.db import Model, OptionsMixin
from nachricht import db


logger = logging.getLogger(__name__)


_language_to_code: Dict[str, str] = {}


def language_code_by_name(language_name):
    global _language_to_code
    if len(_language_to_code) == 0:
        for code in locale_identifiers():
            if not (locale := Locale(code)):
                continue
            if not (name := locale.english_name):
                continue
            _language_to_code[name.lower()] = code
    return _language_to_code.get(language_name.lower())


class Language(Model):
    __tablename__ = "languages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}

    def __repr__(self) -> str:
        return f"<Language(id={self.id}, name={self.name})>"

    @property
    def code(self) -> Optional[str]:
        return language_code_by_name(self.name)

    @property
    def locale(self):
        if not (code := self.code):
            return
        return Locale(code)


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
        identifier = _normalize_language_name(identifier)
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
