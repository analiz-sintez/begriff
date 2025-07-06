import logging
import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
from app import create_app, db
from app.srs import get_notes, Maturity
from app.image import generate_image
from app.auth import User

# Set up logging
logger = logging.getLogger(__name__)


def generate_leech_images():
    """
    Finds all leech notes for all users, generates images for each of them,
    and updates the "image/path" option with the path to the generated image.
    """
    # Fetch all users
    users = User.query.all()

    for user in users:
        logger.info("Generating images for user: %s", user.login)

        notes = get_notes(user_id=user.id, maturity=[Maturity.YOUNG])

        for note in notes:
            if any(card.is_leech() for card in note.cards):
                logger.info("Generating image for leech note: %s", note)
                path = generate_image(note.field2)
                note.set_option("image/path", path)
                db.session.commit()
                logger.info("Image generated and path set for note: %s", note)


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        generate_leech_images()
