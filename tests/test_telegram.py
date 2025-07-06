import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone
import asyncio

from app.telegram.note import _parse_line
from app.telegram.study import handle_study_answer, handle_study_grade
from app.config import Config as DefaultConfig
from app import create_app, db
from app.auth import User, get_user
from app.srs import (
    Note,
    Card,
    Answer,
    create_word_note,
    get_language,
    record_view_start,
    get_card,
)
from app.messenger.telegram import TelegramContext as Context


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


def test_parse_note_line():
    # Test cases for __parse_note_line function
    cases = [
        ("word: explanation", ("word", "explanation")),
        (
            "word with spaces : explanation with spaces",
            ("word with spaces", "explanation with spaces"),
        ),
        ("word: multiline\nexplanation", ("word", "multiline\nexplanation")),
        ("word", ("word", None)),
        ("", (None, None)),
    ]

    for input_text, expected in cases:
        assert _parse_line(input_text) == expected


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


def test_study_session(app):
    Config.FSRS["bury_siblings"] = True
    with app.app_context():
        # Initialize user, language, note, and card
        user = get_user("test_user")
        language = get_language("English")
        note = create_word_note(
            "test_word", "test_explanation", language.id, user.id
        )
        note2 = create_word_note(
            "another_test_word",
            "another_test_explanation",
            language.id,
            user.id,
        )

        # Initialize the card from the note
        first_card = note.cards[0]
        second_card = note.cards[1]

        # Record a new view for the first card
        view_id = record_view_start(first_card.id)

        # Mocking the update and context for handle_study_session
        # TODO make this telegram-agnostic.
        mock_query = AsyncMock()
        mock_user = AsyncMock()
        mock_user.username = user.login
        mock_update = AsyncMock()
        mock_update.callback_query = mock_query
        mock_update.effective_user = mock_user
        mock_context = AsyncMock()
        ctx = Context(mock_update, mock_context)

        # 1. Emulate requesting card answer.
        mock_query.data = f"answer:{first_card.id}"
        # ... due to authorize magic, we must use only keyword arguments here
        asyncio.run(handle_study_answer(ctx=ctx, card_id=first_card.id))
        # ... verify if the answer method on query was called
        # mock_update.message.edit_caption.assert_called_once()

        # 2. Emulate sending card grade.
        mock_query.data = f"grade:{view_id}:good"
        asyncio.run(
            handle_study_grade(
                ctx=ctx,
                view_id=view_id,
                answer=Answer.GOOD,
            )
        )

        # Fetch the updated first card
        updated_first_card = get_card(first_card.id)

        # Verify the first card has non-null stability and difficulty
        assert (
            updated_first_card.stability is not None
        ), "First card stability should not be None."
        assert (
            updated_first_card.difficulty is not None
        ), "First card difficulty should not be None."

        # Verify the first card is scheduled to some date in the future
        assert updated_first_card.ts_scheduled > datetime.now(
            timezone.utc
        ), "First card should be scheduled for a future date."

        # Verify that the second card has a view
        assert (
            len(second_card.views) == 0
        ), "Second card should NOT have another view since siblings are buried."

        assert mock_context.user_data["current_card_id"] not in {
            first_card.id,
            second_card.id,
        }


class MockQuery:
    """A mock query class to simulate SQLAlchemy query."""

    def __init__(self, return_value):
        self.return_value = return_value

    def first(self):
        return self.return_value
