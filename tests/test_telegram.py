import pytest
from telegram import User as TelegramUser, Message, Update
from telegram.ext import CallbackContext
from unittest.mock import MagicMock
from app.telegram.bot import parse_report, handle_message
from app.models import db, User, Report
from app import create_app

def test_parse_report():
    valid_message = "Project/Task/Implement feature: 4.5 (Refactored old code)"
    invalid_message = "Invalid message format"

    # Test valid message parsing
    result = parse_report(valid_message)
    assert result == ("Implement feature", 4.5, "Project", "Task", "Refactored old code")

    # Test message without project and task
    result = parse_report("Implement feature: 3")
    assert result == ("Implement feature", 3, None, None, None)

    # Test invalid message parsing
    with pytest.raises(ValueError):
        parse_report(invalid_message)

class Config:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

@pytest.fixture
def app():
    app = create_app(Config)
    with app.app_context():
        user = User(login='test_user')
        db.session.add(user)
        db.session.commit()
    yield app

def mock_update_with_message(text, username):
    """
    Helper function to create a mock telegram update object
    with given message text and username.
    """
    mock_user = TelegramUser(id=1, first_name="Mock", is_bot=False, username=username)
    mock_message = Message(message_id=1, from_user=mock_user, date=None, chat=None, text=text)
    mock_update = Update(update_id=1, message=mock_message)
    return mock_update

# def test_handle_message(mocker, app):
#     # Ensure application context is used for any DB operations
#     with app.app_context():
#         # Mock the database access and creation
#         mocker.patch('app.telegram.bot.create_report', return_value=MagicMock(description="Implement feature", hours_spent=4.5))

#         # Mock user existence check and creation
#         user = User(login='mock_user')
#         db.session.add(user)
#         db.session.commit()

#         mocker.patch('app.models.User.query.filter_by', return_value=MockQuery(user))

#         # Simulate incoming update from Telegram
#         update = mock_update_with_message("Project/Task/Implement feature: 4.5", 'mock_user')
#         context = MagicMock(CallbackContext)

#         # Call the message handler
#         handle_message(update, context)

#         # Verify that the bot attempted to reply to the message
#         update.message.reply_text.assert_called_once_with('Report created: Implement feature for 4.5 hours.')

class MockQuery:
    """A mock query class to simulate SQLAlchemy query."""
    def __init__(self, return_value):
        self.return_value = return_value

    def first(self):
        return self.return_value
