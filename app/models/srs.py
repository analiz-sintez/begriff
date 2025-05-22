from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Interval
from sqlalchemy.orm import relationship, backref
from datetime import datetime
from enum import Enum
from .core import db, User


class Language(db.Model):
    __tablename__ = 'languages'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name
        }

    def __repr__(self):
        return f"<Language(id={self.id}, name={self.name})>"

    
class Note(db.Model):
    __tablename__ = 'notes'
    id = Column(Integer, primary_key=True)
    field1 = Column(String)
    field2 = Column(String)
    user_id = Column(Integer, ForeignKey(User.id))
    language_id = Column(Integer, ForeignKey(Language.id))
    
    cards = relationship('Card', backref='note', cascade='all, delete-orphan')
    user = relationship('User', backref='notes')
    language = relationship('Language', backref='notes')

    def to_dict(self):
        return {
            'id': self.id,
            'field1': self.field1,
            'field2': self.field2,
            'user_id': self.user_id,
            'language_id': self.language_id
        }

    def __repr__(self):
        return f"<Note(id={self.id}, field1={self.field1}, field2={self.field2}, user_id={self.user_id}, language_id={self.language_id})>"

    
class Card(db.Model):
    __tablename__ = 'cards'
    id = Column(Integer, primary_key=True)
    note_id = Column(Integer, ForeignKey(Note.id))
    front = Column(String, nullable=False)
    back = Column(String, nullable=False)

    views = relationship('View', backref='card', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'note_id': self.note_id,
            'front': self.front,
            'back': self.back
        }

    def __repr__(self):
        return f"<Card(id={self.id}, note_id={self.note_id}, front={self.front}, back={self.back})>"

    
class Answer(Enum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"

    
class View(db.Model):
    __tablename__ = 'views'
    id = Column(Integer, primary_key=True)
    ts_scheduled = Column(DateTime, nullable=False)
    ts_review_finished = Column(DateTime, nullable=False, default=datetime.utcnow)
    ts_review_started = Column(DateTime)
    card_id = Column(Integer, ForeignKey(Card.id))
    review_duration = Column(Interval)
    answer = Column(String)

    def to_dict(self):
        return {
            'id': self.id,
            'ts_scheduled': self.ts_scheduled,
            'ts_viewed': self.ts_review_finished,
            'ts_reviewed': self.ts_review_started,
            'card_id': self.card_id,
            'review_duration': self.review_duration,
            'answer': self.answer
        }

    def __repr__(self):
        return (f"<View(id={self.id}, ts_scheduled={self.ts_scheduled}, "
                f"ts_viewed={self.ts_review_finished}, "
                f"ts_reviewed={self.ts_review_started}, "
                f"card_id={self.card_id}, "
                f"review_duration={self.review_duration}, "
                f"answer={self.answer})>")
