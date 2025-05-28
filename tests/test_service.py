import pytest
from datetime import datetime, timezone, timedelta
from app import create_app, db
from app.models import User, Note, Card, View, Language, Answer
from app.service import (
    create_word_note,
    get_cards,
    record_view_start,
    record_answer,
    get_language,
    get_user,
    update_note,
)


class Config:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture
def app():
    app = create_app(Config)
    with app.app_context():
        # Set up initial test data
        language = Language(name="English")
        user = User(login="test_user")

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
            language_id=get_language("English").id,
            user_id=get_user("test_user").id,
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
            user_id=get_user("test_user").id,
            language_id=get_language("English").id,
            end_ts=end_ts,
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
        assert updated_view.answer == "good"

        # Verify a new view has been created for the next scheduled review of the card
        cards = db.session.query(Card).all()
        assert len(cards) == 2  # Ensure no new card was created

        # The view should now exist for this card (since it's been reviewed)
        card_views = (
            db.session.query(View).filter(View.card_id == card.id).all()
        )
        assert len(card_views) == 1

        # Verify the next scheduled review for the card is in the future
        assert card.ts_last_review is not None
        assert card.ts_scheduled > card.ts_last_review


def test_get_cards_with_bury_siblings(app):
    with app.app_context():
        # Add notes and create corresponding cards
        user_id = get_user("test_user").id
        language_id = get_language("English").id
        text1, explanation1 = "word1", "meaning1"
        text2, explanation2 = "word2", "meaning2"

        create_word_note(
            text=text1,
            explanation=explanation1,
            language_id=language_id,
            user_id=user_id,
        )

        create_word_note(
            text=text2,
            explanation=explanation2,
            language_id=language_id,
            user_id=user_id,
        )

        # Get cards and record a view start and answer for one note's card
        cards = get_cards(user_id=user_id, language_id=language_id)
        assert len(cards) == 4  # Two notes, hence four cards

        # Record view interaction for the first card
        view_id = record_view_start(cards[0].id)
        record_answer(view_id=view_id, answer=Answer.HARD)

        # Test get_cards with bury_siblings flag activated
        end_ts = datetime.now(timezone.utc) + timedelta(days=1)
        filtered_cards = get_cards(
            user_id=user_id,
            language_id=language_id,
            end_ts=end_ts,
            bury_siblings=True,
        )

        # Since one card was reviewed, its sibling should be buried
        assert len(filtered_cards) == 3

        # Ensure the sibling of the reviewed card is buried
        sibling_buried = any(
            card.note_id == cards[0].note_id and card.id != cards[0].id
            for card in filtered_cards
        )
        assert not sibling_buried

        # Ensure that only siblings are buried, not the reviewed card itself
        reviewed_card_included = any(
            card.id == cards[0].id for card in filtered_cards
        )
        assert reviewed_card_included

        # Ensure unrelated cards are not affected
        unrelated_card_included = any(
            card.note_id != cards[0].note_id for card in filtered_cards
        )
        assert unrelated_card_included


def test_update_note_function(app):
    with app.app_context():
        # Add a note to the system
        text = "sample"
        explanation = "a sample explanation"
        note = create_word_note(
            text=text,
            explanation=explanation,
            language_id=get_language("English").id,
            user_id=get_user("test_user").id,
        )

        # Update only the note's field2
        note.field2 = "an updated sample explanation"
        update_note(note)

        # Fetch the updated note
        updated_note = db.session.query(Note).filter_by(id=note.id).first()

        # Verify the note's field2 was updated accordingly
        assert updated_note.field2 == "an updated sample explanation"

        # Check that cards associated with the note are updated with the new field2
        for card in updated_note.cards:
            if card.front == updated_note.field1:
                assert card.back == "an updated sample explanation"
            elif card.back == updated_note.field1:
                assert card.front == "an updated sample explanation"
