import logging
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.types import JSON
from sqlalchemy.ext.mutable import MutableDict
from flask_sqlalchemy import SQLAlchemy

# It's thread-safe while it's from flask_sqlalchemy.
# If replacing flask with fastapi etc, refactor this
# to make thread-safe.
db = SQLAlchemy()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OptionsMixin:
    options = Column(MutableDict.as_mutable(JSON))

    def set_option(self, name, value):
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
        db.session.commit()

    def get_option(self, name, default_value=None):
        if not self.options:
            logger.info(
                "No options set. Returning default value for %s: %s",
                name,
                default_value,
            )
            return default_value
        keys = name.split("/")
        d = self.options
        for key in keys:
            if key not in d:
                logger.info(
                    "Option '%s' not found. Returning default value: %s",
                    name,
                    default_value,
                )
                return default_value
            d = d[key]
        logger.info("Retrieved option: %s = %s", name, d)
        return d


class User(db.Model, OptionsMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    login = Column(String, unique=True)

    def to_dict(self):
        return {"id": self.id, "login": self.login}

    def __repr__(self):
        return f"<User(login='{self.login}')>"
