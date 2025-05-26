import pytest
from datetime import datetime, timezone, timedelta
from app import create_app, db
from app.models import User, Note, Card, View, Language, Answer
from app.service import (
    create_word_note, get_cards, record_view_start, record_answer,
    get_language, get_user)

class Config:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

@pytest.fixture
def app():
    app = create_app(Config)
    with app.app_context():
        # Set up initial test data
        language = Language(name='English')
        user = User(login='test_user')
        
        db.session.add(language)
        db.session.add(user)
        db.session.commit()
    yield app

def test_add_note_and_review(app):
    with app.app_context():
        # 0/ Add a note to the system
        text = "example"
        explanation = "an example explanation"
        create_word_note(
            text=text,
            explanation=explanation,
            language_id=get_language('English').id,
            user_id=get_user('test_user').id
        )

        # Assert the note and cards have been created
        notes = db.session.query(Note).all()
        assert len(notes) == 1

        cards = db.session.query(Card).all()
        assert len(cards) == 2

        # Assert no views have been created initially
        views = db.session.query(View).all()
        assert len(views) == 0
        
        # 1/ Get the next planned card for the test
        end_ts = datetime.now(timezone.utc) + timedelta(days=1)
        cards = get_cards(
            user_id=get_user('test_user').id,
            language_id=get_language('English').id,
            end_ts=end_ts
        )
        assert len(cards) == 2

        # Select the first card for the test
        card = cards[0]

        # 2/ Record view start
        view_id = record_view_start(card_id=card.id)

        # 3/ Record an answer
        record_answer(view_id=view_id, answer=Answer.GOOD)

        # Verify the answer has been recorded
        updated_view = db.session.query(View).filter_by(id=view_id).first()
        assert updated_view.answer == 'good'

        # Verify a new view has been created for the next scheduled review of the card
        cards = db.session.query(Card).all()
        assert len(cards) == 2  # Ensure no new card was created

        # The view should now exist for this card (since it's been reviewed)
        card_views = db.session.query(View).filter(View.card_id == card.id).all()
        assert len(card_views) == 1

        # Verify the next scheduled review for the card is in the future
        assert card.ts_last_review is not None
        assert card.ts_scheduled > card.ts_last_review
