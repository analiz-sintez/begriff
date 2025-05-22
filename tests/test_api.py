import pytest
from app import create_app
from app.models import User, db

class Config:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

@pytest.fixture
def app():
    app = create_app(Config)
    with app.app_context():
        user = User(login='test_user')
        db.session.add(user)
        db.session.commit()
    yield app

@pytest.fixture
def client(app):
    return app.test_client()

def test_put_report(client):
    response = client.put('/report', json={
        'description': 'Test Work',
        'hours_spent': 5,
        'user_id': 1
    })
    assert response.status_code == 200
    assert response.json['message'] == 'Report saved'
    assert 'report_id' in response.json

def test_get_reports(client):
    # First, ensure there's a report to get
    client.put('/report', json={
        'description': 'Test Work',
        'hours_spent': 5,
        'user_id': 1
    })
    
    response = client.get('/report')
    assert response.status_code == 200
    assert len(response.json['reports']) > 0
