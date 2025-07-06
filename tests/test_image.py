import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone
import asyncio

from app.config import Config as DefaultConfig
from app import create_app, db
from app.auth import User, get_user
from app.srs import Note, Card


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
