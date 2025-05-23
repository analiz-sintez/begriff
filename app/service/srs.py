import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from ..models import db, Note, Card, View, Language, Answer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_language(name):
    logger.info("Retrieving language with name: %s", name)
    language = Language.query.filter_by(name=name).first()
    if not language:
        logger.info("Language not found, creating new language: %s", name)
        language = Language(name=name)
        try:
            db.session.add(language)
            db.session.commit()
            logger.info("Language created successfully: %s", language)
        except IntegrityError as e:
            db.session.rollback()
            logger.error("Integrity error occurred while creating a language: %s", e)
            raise ValueError("Integrity error occurred while creating a language.")
    return language


def create_word_note(
        text: str,
        explanation: str,
        language_id: int,
        user_id: int
):
    logger.info("Creating word note with text: '%s', explanation: '%s', language_id: '%d', user_id: '%d'",
                text, explanation, language_id, user_id)
    if not text:
        logger.error("Word or phrase cannot be empty.")
        raise ValueError("Word or phrase cannot be empty.")
    if not user_id or not language_id:
        logger.error("User ID and Language ID must be provided.")
        raise ValueError("User ID and Language ID must be provided.")

    try:
        note = Note(
            field1=text,
            field2=explanation,
            user_id=user_id,
            language_id=language_id)
        db.session.add(note)
        db.session.flush()
        logger.info("Note created: %s", note)
        
        front_card = Card(note_id=note.id, front=text, back=explanation)
        back_card = Card(note_id=note.id, front=explanation, back=text)
        db.session.add_all([front_card, back_card])
        db.session.flush()
        logger.info("Cards created: %s, %s", front_card, back_card)
        
        now = datetime.now(timezone.utc)
        view1 = View(ts_scheduled=now, card_id=front_card.id)
        view2 = View(ts_scheduled=now, card_id=back_card.id)
        db.session.add_all([view1, view2])
        db.session.flush()
        logger.info("Views scheduled: %s, %s", view1, view2)
        
        db.session.commit()
        logger.info("Transaction committed successfully for word note creation.")
    except IntegrityError as e:
        db.session.rollback()
        logger.error("Integrity error occurred: %s", e)
        raise e


def get_view(view_id: int):
    logger.info("Getting view by id '%d'", view_id)
    return View.query.filter_by(id=view_id).first()


def get_views(
        user_id: int,
        language_id: int,
        answer: Answer = None,
        time_interval: tuple = None
):
    logger.info("Getting views for user_id: '%d', language_id: '%d', answer: '%s', time_interval: '%s'",
                user_id, language_id, answer, time_interval)
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

    results = query.all()
    logger.info("Retrieved %i views", len(results))
    logger.debug("\n".join([str(view) for view in results]))
    return results


def record_view_start(view_id: int):
    logger.info("Recording view start for view_id: '%d'", view_id)
    view = db.session.query(View).filter_by(id=view_id).first()
    if view:
        view.ts_review_started = datetime.now(timezone.utc)
        db.session.commit()
        logger.info("View start recorded and transaction committed: %s", view)

        
def record_answer(view_id: int, answer: Answer):
    logger.info("Recording answer for view_id: '%d', answer: '%s'", view_id, answer)
    view = db.session.query(View).filter_by(id=view_id).first()
    if view:
        view.answer = answer.value
        view.ts_review_finished = datetime.now(timezone.utc)
        next_view = View(
            ts_scheduled=datetime.now(timezone.utc) + timedelta(minutes=10),
            card_id=view.card_id)
        db.session.add(next_view)
        db.session.commit()
        logger.info("Answer recorded and next view scheduled: %s, %s", view, next_view)
