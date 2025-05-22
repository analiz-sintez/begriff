import pytest
from datetime import datetime, timezone, timedelta
from app import create_app, db
from app.models import User, Note, Card, View, Language, Answer
from app.service import (
    create_word_note, get_views, record_view_start, record_answer,
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

        views = db.session.query(View).all()
        assert len(views) == 2
        
        # 1/ Get the next planned view
        views = get_views(
            user_id=get_user('test_user').id,
            language_id=get_language('English').id
        )
        assert len(views) == 2

        # Select the first view for the test
        # (we assume views have been scheduled immediately upon note creation)
        view = views[0]

        # 2/ Record view start
        record_view_start(view_id=view.id)

        # 3/ Record an answer
        record_answer(view_id=view.id, answer=Answer.GOOD)

        # Verify the answer has been recorded
        updated_view = db.session.query(View).filter_by(id=view.id).first()
        assert updated_view.answer == 'good'

        # Verify a new view has been created, and there are still 2 views
        new_views = (db.session.query(View)
                     .filter(View.id != updated_view.id)
                     .filter(View.card_id == updated_view.card_id)
                     ).all()
        assert len(new_views) == 1
        new_view = new_views[0]

        # Verify the next scheduled view is in the future (at least 10 minutes later)
        assert new_view.ts_scheduled > updated_view.ts_review_finished
