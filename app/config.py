import os

basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class Config:
    # List of allowed Telegram users
    ALLOWED_USERS = [
        # Add Telegram logins here
        'user1',
        'user2',
        'user3'
    ]
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        "sqlite:///" + os.path.join(basedir, 'data/database.sqlite')
    
    # Swagger configuration
    SWAGGER = {
        'title': 'Co-op Bot API',
        'uiversion': 3,
        'openapi': '3.0.0'
    }
