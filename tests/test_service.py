import pytest
from app import create_app, db
from app.service import create_report, get_reports
from app.models import User

class Config:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

@pytest.fixture
def app():
    app = create_app(Config)
    with app.app_context():
        # Set up initial test data
        user = User(login='test_user')
        db.session.add(user)
        db.session.commit()
    yield app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

def test_create_report(app):
    with app.app_context():
        user = User.query.filter_by(login='test_user').first()
        # Create report and check that it's properties are set up ok.
        report = create_report(
            description='Test Work',
            hours_spent=5,
            user_id=user.id
        )
        assert report.description == 'Test Work'
        assert report.hours_spent == 5

def test_get_reports(app):
    with app.app_context():
        # Add a report
        user = db.session.query(User).filter_by(login='test_user').first()
        report = create_report(
            description='Another Test',
            hours_spent=4,
            user_id=user.id
        )
        db.session.add(report)
        db.session.commit()

        reports = get_reports()
        assert len(reports) == 1  # Assuming one report created in a previous test
        report = get_reports(user_id=user.id)[0]
        assert report.description == "Another Test"
        assert report.hours_spent == 4
        
