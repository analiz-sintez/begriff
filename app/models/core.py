from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime
from sqlalchemy.sql import func
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    login = Column(String, unique=True)

    def to_dict(self):
        return {
            'id': self.id,
            'login': self.login
        }

    def __repr__(self):
        return f"<User(login='{self.login}'>"
