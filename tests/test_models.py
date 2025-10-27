import pytest
from datetime import datetime, timedelta, timezone

from nachricht import create_app, db
from nachricht.auth import User, get_user
from app import Config, combine
from app.notes import WordNote, Language, get_native_language
from app.srs import Card, View, DirectCard, ReverseCard


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    DEFAULTS = {
        "study_language": "english",
        "native_language": "english",
    }


combine(Config, TestConfig)


@pytest.fixture
def app():
    app = create_app(Config)
    with app.app_context():
        # Set up initial test data
        language = Language(name="English")
        user = get_user("test_user")
        note = WordNote(
            field1="Hello", field2="World", user=user, language=language
        )
        db.session.add(language)
        db.session.add(user)
        db.session.add(note)
        db.session.flush()

        card = DirectCard(
            note=note,
            ts_scheduled=datetime.now(timezone.utc),
            stability=0.5,
            difficulty=0.5,
        )
        view = View(
            card=card,
            ts_review_started=datetime.now(timezone.utc),
            ts_review_finished=datetime.now(timezone.utc),
        )

        db.session.add(card)
        db.session.add(view)
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


def test_note_creation(app):
    with app.app_context():
        # user = User.query.filter_by(login="test_user").first()
        user = get_user("test_user")
        assert get_native_language(user).code == "en"
        language = Language.query.filter_by(name="English").first()
        note = WordNote(
            field1="Test", field2="Note", user=user, language=language
        )

        db.session.add(note)
        db.session.commit()

        fetched_note = WordNote.query.filter_by(
            field1="Test", field2="Note"
        ).first()
        assert fetched_note is not None
        assert fetched_note.field1 == "Test"
        assert fetched_note.field2 == "Note"
        assert fetched_note.user == user
        assert fetched_note.language == language


def test_view_relationship(app):
    with app.app_context():
        card = Card.query.first()
        view = View.query.filter_by(card_id=card.id).first()

        assert view is not None
        assert view.card == card


@pytest.mark.asyncio
async def test_card_creation(app):
    with app.app_context():
        user = User.query.filter_by(login="test_user").first()
        language = Language.query.filter_by(name="English").first()
        note = WordNote(
            field1="Test", field2="Note", user=user, language=language
        )

        db.session.add(note)
        db.session.commit()

        card = ReverseCard(
            note=note,
            ts_scheduled=datetime.now(timezone.utc),
            stability=0.75,
            difficulty=0.25,
        )

        db.session.add(card)
        db.session.commit()

        fetched_card = Card.query.filter_by(note_id=note.id).first()
        assert fetched_card is not None
        assert fetched_card.note == note
        assert isinstance(fetched_card, ReverseCard)
        front = await fetched_card.get_front()
        assert "text" in front
        assert note.field2 in front["text"]
        back = await fetched_card.get_back()
        assert "text" in back
        assert note.field1 in back["text"]
        assert fetched_card.stability == 0.75
        assert fetched_card.difficulty == 0.25


def test_language_creation(app):
    with app.app_context():
        language = Language(name="French")

        db.session.add(language)
        db.session.commit()

        fetched_language = Language.query.filter_by(name="French").first()
        assert fetched_language is not None
        assert fetched_language.name == "French"


def test_user_options(app):
    with app.app_context():
        user = User.query.filter_by(login="test_user").first()

        # Set and persist user options
        user.set_option("notifications/enable", True)
        user.set_option("theme/color", "dark")

        # Fetch the user again to simulate a fresh retrieval
        fetched_user = User.query.filter_by(login="test_user").first()

        assert fetched_user.get_option("notifications/enable") is True
        assert fetched_user.get_option("theme/color") == "dark"
        assert (
            fetched_user.get_option("nonexistent/option", "default")
            == "default"
        )
