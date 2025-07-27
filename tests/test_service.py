import pytest
from datetime import datetime, timezone, timedelta

from core import create_app, db
from core.auth import User, get_user

from app.config import Config as DefaultConfig
from app.notes import Note, Language
from app.srs.models import Card, View, Answer
from app.srs import (
    create_word_note,
    get_cards,
    get_notes,
    record_view_start,
    record_answer,
    get_language,
    update_note,
    Maturity,
)


class Config(DefaultConfig):
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


def test_get_notes_filters(app):
    with app.app_context():
        user_id = get_user("test_user").id
        language_id = get_language("English").id

        create_word_note(
            text="apple",
            explanation="a fruit",
            language_id=language_id,
            user_id=user_id,
        )

        create_word_note(
            text="banana",
            explanation="another fruit",
            language_id=language_id,
            user_id=user_id,
        )

        create_word_note(
            text="cat",
            explanation="an animal",
            language_id=language_id,
            user_id=user_id,
        )

        # Test text filter
        notes = get_notes(
            user_id=user_id, language_id=language_id, text="apple"
        )
        assert len(notes) == 1
        assert notes[0].field1 == "apple"

        # Test regex filter on text
        notes = get_notes(
            user_id=user_id, language_id=language_id, text="=~^a.*"
        )
        assert len(notes) == 1
        assert notes[0].field1 == "apple"

        # Test SQL LIKE filter on text
        notes = get_notes(user_id=user_id, language_id=language_id, text="a%")
        assert len(notes) == 1
        fetched_texts = {note.field1 for note in notes}
        assert "apple" in fetched_texts
        assert "banana" not in fetched_texts

        # Test explanation filter
        notes = get_notes(
            user_id=user_id, language_id=language_id, explanation="animal"
        )
        assert len(notes) == 0

        # Test regex filter on explanation
        notes = get_notes(
            user_id=user_id, language_id=language_id, explanation="=~^an.*"
        )
        assert len(notes) == 2
        fetched_explanations = {note.field2 for note in notes}
        assert "an animal" in fetched_explanations
        assert "a fruit" not in fetched_explanations

        # Test SQL LIKE filter on explanation
        notes = get_notes(
            user_id=user_id, language_id=language_id, explanation="an%"
        )
        assert len(notes) == 2
        fetched_explanations = {note.field2 for note in notes}
        assert "an animal" in fetched_explanations
        assert "a fruit" not in fetched_explanations


def test_maturity_filter(app):
    with app.app_context():
        user_id = get_user("test_user").id
        language_id = get_language("English").id

        note1 = create_word_note(
            text="zebra",
            explanation="a striped animal",
            language_id=language_id,
            user_id=user_id,
        )

        note2 = create_word_note(
            text="elephant",
            explanation="a large mammal",
            language_id=language_id,
            user_id=user_id,
        )

        note3 = create_word_note(
            text="lion",
            explanation="king of the jungle",
            language_id=language_id,
            user_id=user_id,
        )

        # Simulate reviews to modify maturity
        card1 = note1.cards[0]
        card2a = note2.cards[0]
        card2b = note2.cards[1]
        card3 = note3.cards[0]

        # Note1: Make it YOUNG, set review intervals to tomorrow
        view_id1 = record_view_start(card1.id)
        record_answer(view_id1, Answer.GOOD)
        card1.ts_scheduled = datetime.now(timezone.utc) - timedelta(days=1)
        db.session.commit()

        # Note2: Make it MATURE, set review intervals beyond 2 days
        view_id2a = record_view_start(card2a.id)
        record_answer(view_id2a, Answer.GOOD)
        card2a.ts_scheduled = datetime.now(timezone.utc) + timedelta(
            days=Config.FSRS["mature_threshold"] + 1
        )
        view_id2b = record_view_start(card2b.id)
        record_answer(view_id2b, Answer.GOOD)
        card2b.ts_scheduled = datetime.now(timezone.utc) + timedelta(
            days=Config.FSRS["mature_threshold"] + 1
        )
        db.session.commit()

        # Note3 is still NEW as it hasn't been reviewed yet

        # Test maturity filter
        notes_new = get_notes(
            user_id=user_id, language_id=language_id, maturity=[Maturity.NEW]
        )
        assert len(notes_new) == 1
        assert notes_new[0].field1 == "lion"

        notes_young = get_notes(
            user_id=user_id, language_id=language_id, maturity=[Maturity.YOUNG]
        )
        assert len(notes_young) == 1
        assert notes_young[0].field1 == "zebra"

        notes_mature = get_notes(
            user_id=user_id,
            language_id=language_id,
            maturity=[Maturity.MATURE],
        )
        assert len(notes_mature) == 1
        assert notes_mature[0].field1 == "elephant"
