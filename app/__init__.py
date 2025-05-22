import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flasgger import Swagger

from .models import db

def create_app(config=None):
    app = Flask(__name__)
    if not config:
        from .config import Config as config

    app.config.from_object(config)

    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    db.init_app(app)

    with app.app_context():
        db.create_all()
        logger.info("Database tables created.")

    migrate = Migrate(app, db)
    logger.info("Migrations set up.")

    # Import and register blueprints here
    from .routes import srs_bp
    app.register_blueprint(srs_bp)
    logger.info("Blueprints registered.")

    # Initialize Swagger
    swagger = Swagger(app, template_file="./swagger/api_docs.yaml")
    logger.info("Swagger documentation set up.")

    logger.info("Application setup complete.")

    return app
