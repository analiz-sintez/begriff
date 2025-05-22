from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from enum import Enum
from ..models import db, Note, Card, View, User, Language


class Answer(Enum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"

    
def create_word_note(
        text: str,
        explanation: str,
        language_id: int,
        user_id: int
):
    # Sanity check inputs
    if not text:
        raise ValueError("Word or phrase cannot be empty.")
    if not user_id or not language_id:
        raise ValueError("User ID and Language ID must be provided.")

    try:
        # Create note
        note = Note(
            field1=text,
            field2=explanation,
            user_id=user_id,
            language_id=language_id)
        db.session.add(note)
        
        # Create two cards
        front_card = Card(note_id=note.id, front=text, back=explanation)
        back_card = Card(note_id=note.id, front=explanation, back=text)
        db.session.add_all([front_card, back_card])
        
        # Schedule views for immediate study
        now = datetime.now(timezone.utc)
        view1 = View(ts_scheduled=now, card_id=front_card.id)
        view2 = View(ts_scheduled=now, card_id=back_card.id)
        db.session.add_all([view1, view2])
        
        # ... save all changes in a row
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        raise e

    
def get_views(
        user_id: int,
        language_id: int,
        answer: Answer = None,
        time_interval: tuple = None
):
    query = db.session.query(View).join(Card).join(Note)
    query = query.filter(Note.user_id == user_id)
    query = query.filter(Note.language_id == language_id)

    if answer:
        query = query.filter(View.answer == answer.value)

    if time_interval:
        start, end = time_interval
        query = query.filter(
            View.ts_scheduled > start,
            View.ts_scheduled <= end)

    return query.all()


def record_view_start(view_id: int):
    view = db.session.query(View).filter_by(id=view_id).first()
    if view:
        view.ts_review_started = datetime.now(timezone.utc)
        db.session.commit()

        
def record_answer(view_id: int, answer: Answer):
    view = db.session.query(View).filter_by(id=view_id).first()
    if view:
        view.answer = answer.value
        view.ts_review_finished = datetime.now(timezone.utc)
        # Create next scheduled view
        next_view = View(
            ts_scheduled=datetime.now(timezone.utc) + timedelta(minutes=10),
            card_id=view.card_id)
        db.session.add(next_view)
        db.session.commit()
