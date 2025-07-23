# Please write a script which takes traverses all notes, checks if they have `translations/<language.id>` option, and if so, copies it into `explanations/<language.code>` option and clears the previous one.
# You need to check if <language.id> found is a correct id of an existing language. If not, skip this entry. If yes, get the code from `Language.code` property.

import logging

from flask.cli import with_appcontext
import click

from core import create_app
from core.db import db, flag_modified
from app.srs import Note, get_language
from app.config import Config

logger = logging.getLogger(__name__)


@click.command("migrate-translations")
def migrate_translations_command():
    """
    Migrates note options from 'translations/<lang_id>' to 'explanations/<lang_code>'.

    This script iterates through all notes. For each note, it inspects the `options`
    JSON field. If it finds a structure like `{"translations": {"<ID>": "..."}}`,
    it validates the language ID, gets the corresponding language code, and moves
    the translation to `{"explanations": {"<CODE>": "..."}}`.
    The original entry under `translations` is then removed.
    """
    app = create_app(Config)
    with app.app_context():
        logger.info("Starting translation options migration.")

        notes_with_options = Note.query.filter(Note.options.isnot(None)).all()
        logger.info(
            f"Found {len(notes_with_options)} notes with options to process."
        )

        notes_updated_count = 0
        for note in notes_with_options:
            if not isinstance(note.options, dict):
                continue

            if not isinstance(note.options.get("translations"), dict):
                continue

            made_change = False
            translations_dict = note.options["translations"]

            for lang_id_str in list(translations_dict.keys()):
                try:
                    lang_id = int(lang_id_str)
                except (ValueError, TypeError):
                    logger.debug(
                        f"Note {note.id}: Key '{lang_id_str}' is not a language ID. Skipping."
                    )
                    continue

                language = get_language(lang_id)
                if not language:
                    logger.warning(
                        f"Note {note.id}: Language with ID {lang_id} not found. Cannot migrate."
                    )
                    continue

                if not language.code:
                    logger.warning(
                        f"Note {note.id}: Language '{language.name}' (ID: {lang_id}) has no code. Cannot migrate."
                    )
                    continue

                translation_value = translations_dict[lang_id_str]

                if "explanations" not in note.options or not isinstance(
                    note.options.get("explanations"), dict
                ):
                    note.options["explanations"] = {}

                note.options["explanations"][language.code] = translation_value
                logger.info(
                    f"Note {note.id}: Migrated 'translations/{lang_id}' to 'explanations/{language.code}'."
                )

                del translations_dict[lang_id_str]
                made_change = True

            if not note.options.get("translations"):
                del note.options["translations"]
                logger.info(
                    f"Note {note.id}: Removed empty 'translations' dictionary."
                )

            if made_change:
                flag_modified(note, "options")
                notes_updated_count += 1

        if notes_updated_count > 0:
            try:
                db.session.commit()
                logger.info(
                    f"Migration complete. Committed changes for {notes_updated_count} notes."
                )
            except Exception as e:
                db.session.rollback()
                logger.error(
                    f"Failed to commit changes to the database: {e}",
                    exc_info=True,
                )
        else:
            logger.info("Migration complete. No notes required changes.")


if __name__ == "__main__":
    migrate_translations_command()
