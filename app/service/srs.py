from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..models import Note, Card, View, User, Language


def create_word_note(session: Session, text: str, explanation: str, language_id: int, user_id: int):
    # Sanity check inputs
    if not text:
        raise ValueError("Word or phrase cannot be empty.")
    if not user_id or not language_id:
        raise ValueError("User ID and Language ID must be provided.")

    try:
        # Create note
        note = Note(field1=text, field2=explanation, user_id=user_id, language_id=language_id)
        session.add(note)
        session.commit()

        # Create two cards
        front_card = Card(note_id=note.id, front=text, back=explanation)
        back_card = Card(note_id=note.id, front=explanation, back=text)
        session.add_all([front_card, back_card])
        session.commit()

        # Schedule views for immediate study
        now = datetime.utcnow()
        view1 = View(ts_scheduled=now, card_id=front_card.id)
        view2 = View(ts_scheduled=now, card_id=back_card.id)
        session.add_all([view1, view2])
        session.commit()

    except IntegrityError as e:
        session.rollback()
        raise e


def get_views(session: Session, user_id: int, language_id: int, answer: str = None, time_interval: tuple = None):
    query = session.query(View).join(Card).join(Note)
    query = query.filter(Note.user_id == user_id)
    query = query.filter(Note.language_id == language_id)

    if answer:
        query = query.filter(View.answer == answer)

    if time_interval:
        start, end = time_interval
        query = query.filter(View.ts_scheduled >= start, View.ts_scheduled <= end)

    return query.all()


def record_view_start(session: Session, view_id: int):
    view = session.query(View).filter_by(id=view_id).first()
    if view:
        view.ts_review_started = datetime.utcnow()
        session.commit()


def record_answer(session: Session, view_id: int, answer: str):
    view = session.query(View).filter_by(id=view_id).first()
    if view:
        view.answer = answer
        view.ts_review_finished = datetime.utcnow()
        # Create next scheduled view
        next_view = View(ts_scheduled=datetime.utcnow() + timedelta(minutes=10), card_id=view.card_id)
        session.add(next_view)
        session.commit()
