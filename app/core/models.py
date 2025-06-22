import logging
from typing import Union, Dict, List, TypeAlias

from sqlalchemy import Integer, String
from sqlalchemy.orm import mapped_column, DeclarativeBase
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.types import JSON
from sqlalchemy.ext.mutable import MutableDict
from flask_sqlalchemy import SQLAlchemy


class BaseModel(DeclarativeBase):
    """
    This one is required to calm down pyright.
    see: https://github.com/pallets-eco/flask-sqlalchemy/issues/1327
    """

    pass


# It's thread-safe while it's from flask_sqlalchemy.
# If replacing flask with fastapi etc, refactor this
# to make thread-safe.
db = SQLAlchemy(model_class=BaseModel)
Model: BaseModel = db.Model  # pyright: ignore

# Set up logging

logger = logging.getLogger(__name__)


JsonValue: TypeAlias = Union[
    Dict[str, "JsonValue"], List["JsonValue"], str, int, float, bool, None
]


class OptionsMixin:
    options = mapped_column(MutableDict.as_mutable(JSON))

    def set_option(self, name: str, value) -> None:
        if self.options is None:
            self.options = {}
        keys = name.split("/")
        d = self.options
        for key in keys[:-1]:
            if key not in d or not isinstance(d[key], dict):
                d[key] = {}
            d = d[key]
        d[keys[-1]] = value
        logger.info("Setting option for: %s = %s", name, value)
        flag_modified(self, "options")
        db.session.add(self)
        db.session.commit()

    def get_option(self, name: str, default_value=None) -> JsonValue:
        if not self.options:
            logger.debug(
                "No options set. Returning default value for %s: %s",
                name,
                default_value,
            )
            return default_value
        keys = name.split("/")
        d = self.options
        for key in keys:
            if key not in d:
                logger.debug(
                    "Option '%s' not found. Returning default value: %s",
                    name,
                    default_value,
                )
                return default_value
            d = d[key]
        logger.debug("Retrieved option: %s = %s", name, d)
        return d


class User(Model, OptionsMixin):
    __tablename__ = "users"

    id = mapped_column(Integer, primary_key=True)
    login = mapped_column(String, unique=True)

    def to_dict(self):
        return {"id": self.id, "login": self.login}

    def __repr__(self):
        return f"<User(login='{self.login}')>"
