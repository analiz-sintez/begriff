import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone
import asyncio

from app.telegram.note import __parse_note_line
from app.telegram.note_list import format_note
from app.telegram.study import handle_study_session
from app.config import Config as DefaultConfig
from app import create_app
from app.core import db, User, get_user
from app.srs import (
    Note,
    Card,
    create_word_note,
    get_language,
    record_view_start,
    get_card,
)


class Config(DefaultConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture
def app():
    app = create_app(Config)
    with app.app_context():
        user = User(login="test_user")
        db.session.add(user)
        db.session.commit()
    yield app
