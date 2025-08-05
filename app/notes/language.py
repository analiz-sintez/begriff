import logging
from typing import Optional, Dict, Union

from sqlalchemy import (
    Integer,
    String,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import mapped_column, Mapped
from babel import Locale
from babel.localedata import locale_identifiers
from flag import flag

from nachricht import db
from nachricht.db import Model
from nachricht.auth import User

from .. import Config


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

    @classmethod
    def from_id(cls, id: int) -> "Language":
        return get_language(id)

    @classmethod
    def from_locale(cls, locale: Locale) -> "Language":
        name = locale.get_language_name("en")
        return get_language(name)

    @classmethod
    def from_name(cls, name: str) -> "Language":
        return get_language(name)

    @classmethod
    def from_code(cls, code: str) -> "Language":
        locale = Locale.parse(code)
        return cls.from_locale(locale)

    @property
    def code(self) -> Optional[str]:
        return language_code_by_name(self.name)

    @property
    def locale(self):
        if not (code := self.code):
            return
        return Locale(code)

    def get_localized_name(self, locale: Locale) -> str:
        if not self.locale:
            return self.name
        return self.locale.get_language_name(locale.language)

    @property
    def flag(self) -> str:
        """Return the language flag, or if we can't find it, the language name."""
        if not self.locale:
            return "?"
        if terr := Config.LANGUAGE["territories"].get(self.locale.language):
            return flag(terr)
        return self.name


def get_native_language(user: User):
    default = Config.LANGUAGE["defaults"]["native"]
    return get_language(user.get_option("native_language", default))


def get_studied_language(user: User):
    default = Config.LANGUAGE["defaults"]["study"]
    return get_language(user.get_option("studied_language", default))


def _normalize_language_name(name: str) -> str:
    return name[:1].upper() + name[1:].lower()


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
        logger.debug("Retrieving language with name: %s", identifier)
        language = Language.query.filter_by(name=identifier).first()
    elif isinstance(identifier, int):
        logger.debug("Retrieving language with id: %d", identifier)
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
