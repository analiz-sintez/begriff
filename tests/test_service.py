import pytest
from app import create_app, db
from app.service import create_report, get_reports
from app.models import User, Note, Card, View, Language
from datetime import datetime, timedelta

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
        note = Note(field1='Hello', field2='World', user=user, language=language)
        card = Card(note=note, front='Hello', back='World')
        view = View(
            card=card, ts_scheduled=datetime.utcnow(),
            ts_review_finished=datetime.utcnow())
        
        db.session.add(language)
        db.session.add(user)
        db.session.add(note)
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
        user = User.query.filter_by(login='test_user').first()
        language = Language.query.filter_by(name='English').first()
        note = Note(field1='Test', field2='Note', user=user, language=language)
        
        db.session.add(note)
        db.session.commit()

        fetched_note = Note.query.filter_by(field1='Test', field2='Note').first()
        assert fetched_note is not None
        assert fetched_note.field1 == 'Test'
        assert fetched_note.field2 == 'Note'
        assert fetched_note.user == user
        assert fetched_note.language == language

def test_view_relationship(app):
    with app.app_context():
        card = Card.query.first()
        view = View.query.filter_by(card_id=card.id).first()
        
        assert view is not None
        assert view.card == card

def test_card_creation(app):
    with app.app_context():
        note = Note.query.first()
        card = Card(note=note, front='Test Front', back='Test Back')
        
        db.session.add(card)
        db.session.commit()

        fetched_card = Card.query.filter_by(front='Test Front', back='Test Back').first()
        assert fetched_card is not None
        assert fetched_card.front == 'Test Front'
        assert fetched_card.back == 'Test Back'
        assert fetched_card.note == note

def test_language_creation(app):
    with app.app_context():
        language = Language(name='French')
        
        db.session.add(language)
        db.session.commit()

        fetched_language = Language.query.filter_by(name='French').first()
        assert fetched_language is not None
        assert fetched_language.name == 'French'
