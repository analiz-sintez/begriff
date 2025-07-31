import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone
import asyncio

from nachricht import create_app, db
from nachricht.auth import User, get_user

from app.srs import Note, Card
from app.config import Config as DefaultConfig


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
