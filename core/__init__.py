import logging
from flask import Flask
from flask_migrate import Migrate

from .db import db


def create_app(config: object):
    app = Flask(__name__)
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

    logger.info("Application setup complete.")

    return app
