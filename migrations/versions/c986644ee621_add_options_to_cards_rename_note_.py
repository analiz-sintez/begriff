"""Add options to cards, rename Note.explanations option to translations

Revision ID: c986644ee621
Revises: 1a1161652780
Create Date: 2025-07-24 12:57:39.313101

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c986644ee621"
down_revision = "1a1161652780"
branch_labels = None
depends_on = None


import json
from sqlalchemy import table, column, select, update, Integer, String, JSON
from babel import Locale
from babel.localedata import locale_identifiers


# Define table schemas for use with op.execute
notes_table = table("notes", column("id", Integer), column("options", JSON))
languages_table = table(
    "languages", column("id", Integer), column("name", String)
)


def _get_lang_code_by_name_map():
    """Replicates the logic from app.srs.models.language_code_by_name to avoid app import."""
    lang_code_map = {}
    for code in locale_identifiers():
        if not (locale := Locale(code)):
            continue
        if not (name := locale.english_name):
            continue
        lang_code_map[name.lower()] = code
    return lang_code_map


def upgrade_note_options():
    # ### Data migration from 'translations/<lang_id>' to 'explanations/<lang_code>' ###
    conn = op.get_bind()

    # 1. Fetch all languages and create a map from ID to code
    lang_name_to_code_map = _get_lang_code_by_name_map()
    lang_id_to_code_map = {}
    lang_results = conn.execute(
        select(languages_table.c.id, languages_table.c.name)
    )
    for lang_id, lang_name in lang_results:
        lang_code = lang_name_to_code_map.get(lang_name.lower())
        if lang_code:
            lang_id_to_code_map[lang_id] = lang_code

    # 2. Fetch all notes that have options
    notes_results = conn.execute(
        select(notes_table.c.id, notes_table.c.options).where(
            notes_table.c.options.isnot(None)
        )
    )

    # 3. Iterate through notes and perform migration
    for note_id, options_json in notes_results:
        if not options_json:
            continue

        # In some DBs (like SQLite), this is a string, in others a dict.
        options = (
            json.loads(options_json)
            if isinstance(options_json, str)
            else options_json
        )

        if (
            not isinstance(options, dict)
            or "translations" not in options
            or not isinstance(options.get("translations"), dict)
        ):
            continue

        translations_dict = options["translations"]
        made_change = False

        for lang_id_str in list(translations_dict.keys()):
            try:
                lang_id = int(lang_id_str)
            except (ValueError, TypeError):
                continue

            if lang_code := lang_id_to_code_map.get(lang_id):
                translation_value = translations_dict.pop(lang_id_str)

                if "explanations" not in options or not isinstance(
                    options.get("explanations"), dict
                ):
                    options["explanations"] = {}

                options["explanations"][lang_code] = translation_value
                made_change = True

        if not options.get("translations"):
            options.pop("translations", None)

        if made_change:
            op.execute(
                update(notes_table)
                .where(notes_table.c.id == note_id)
                .values(options=json.dumps(options))
            )


def downgrade_note_options():
    # ### Data migration from 'explanations/<lang_code>' back to 'translations/<lang_id>' ###
    conn = op.get_bind()

    # 1. Fetch all languages and create a map from code to ID
    lang_name_to_code_map = _get_lang_code_by_name_map()
    lang_code_to_id_map = {}
    lang_results = conn.execute(
        select(languages_table.c.id, languages_table.c.name)
    )
    for lang_id, lang_name in lang_results:
        lang_code = lang_name_to_code_map.get(lang_name.lower())
        if lang_code:
            lang_code_to_id_map[lang_code] = lang_id

    # 2. Fetch all notes that have options
    notes_results = conn.execute(
        select(notes_table.c.id, notes_table.c.options).where(
            notes_table.c.options.isnot(None)
        )
    )

    # 3. Iterate through notes and perform reverse migration
    for note_id, options_json in notes_results:
        if not options_json:
            continue

        options = (
            json.loads(options_json)
            if isinstance(options_json, str)
            else options_json
        )

        if (
            not isinstance(options, dict)
            or "explanations" not in options
            or not isinstance(options.get("explanations"), dict)
        ):
            continue

        explanations_dict = options["explanations"]
        made_change = False

        for lang_code in list(explanations_dict.keys()):
            if lang_id := lang_code_to_id_map.get(lang_code):
                explanation_value = explanations_dict.pop(lang_code)

                if "translations" not in options or not isinstance(
                    options.get("translations"), dict
                ):
                    options["translations"] = {}

                options["translations"][str(lang_id)] = explanation_value
                made_change = True

        if not options.get("explanations"):
            options.pop("explanations", None)

        if made_change:
            op.execute(
                update(notes_table)
                .where(notes_table.c.id == note_id)
                .values(options=json.dumps(options))
            )


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.add_column(sa.Column("options", sa.JSON(), nullable=True))
        batch_op.alter_column(
            "note_id", existing_type=sa.INTEGER(), nullable=False
        )

    with op.batch_alter_table("languages", schema=None) as batch_op:
        batch_op.alter_column(
            "name", existing_type=sa.VARCHAR(), nullable=False
        )

    with op.batch_alter_table("notes", schema=None) as batch_op:
        batch_op.alter_column(
            "field1", existing_type=sa.VARCHAR(), nullable=False
        )

    with op.batch_alter_table("views", schema=None) as batch_op:
        batch_op.alter_column(
            "ts_review_started", existing_type=sa.DATETIME(), nullable=False
        )
        batch_op.alter_column(
            "card_id", existing_type=sa.INTEGER(), nullable=False
        )

    # ### end Alembic commands ###
    upgrade_note_options()


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("views", schema=None) as batch_op:
        batch_op.alter_column(
            "card_id", existing_type=sa.INTEGER(), nullable=True
        )
        batch_op.alter_column(
            "ts_review_started", existing_type=sa.DATETIME(), nullable=True
        )

    with op.batch_alter_table("notes", schema=None) as batch_op:
        batch_op.alter_column(
            "field1", existing_type=sa.VARCHAR(), nullable=True
        )

    with op.batch_alter_table("languages", schema=None) as batch_op:
        batch_op.alter_column(
            "name", existing_type=sa.VARCHAR(), nullable=True
        )

    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.alter_column(
            "note_id", existing_type=sa.INTEGER(), nullable=True
        )
        batch_op.drop_column("options")

    # ### end Alembic commands ###
    downgrade_note_options()
