from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime
from sqlalchemy.orm import relationship
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

class Project(db.Model):
    __tablename__ = 'projects'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    created_dttm = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'created_dttm': self.created_dttm.isoformat() if self.created_dttm else None
        }

class Task(db.Model):
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    project_id = Column(Integer, ForeignKey('projects.id'))
    created_dttm = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'project_id': self.project_id,
            'created_dttm': self.created_dttm.isoformat() if self.created_dttm else None
        }

class Report(db.Model):
    __tablename__ = 'reports'

    id = Column(Integer, primary_key=True)
    description = Column(String)
    hours_spent = Column(Float)
    comment = Column(String)
    result = Column(String)
    difficulty = Column(String)
    remaining_estimate = Column(Float)
    user_id = Column(Integer, ForeignKey('users.id'))
    task_id = Column(Integer, ForeignKey('tasks.id'))
    created_dttm = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    task = relationship("Task")

    def to_dict(self):
        return {
            'id': self.id,
            'description': self.description,
            'hours_spent': self.hours_spent,
            'comment': self.comment,
            'result': self.result,
            'difficulty': self.difficulty,
            'remaining_estimate': self.remaining_estimate,
            'user_id': self.user_id,
            'task_id': self.task_id,
            'created_dttm': self.created_dttm.isoformat() if self.created_dttm else None,
            'user': self.user.to_dict() if self.user else None,
            'task': self.task.to_dict() if self.task else None
        }
