import json
from sqlalchemy import (
    create_engine,
    select,
    table,
    column,
    Integer,
    JSON,
    update,
)


notes_table = table("notes", column("id", Integer), column("options", JSON))

engine = create_engine("sqlite:///./data/database.sqlite")
with engine.connect() as conn:
    notes_results = conn.execute(
        select(notes_table.c.id, notes_table.c.options).where(
            notes_table.c.options.isnot(None)
        )
    )
    for note_id, options in notes_results:
        # options = json.loads(options_str)
        if isinstance(options, dict):
            continue
        options_dict = json.loads(options)
        print(note_id, options_dict)

        conn.execute(
            update(notes_table)
            .where(notes_table.c.id == note_id)
            .values(options=options_dict)
        )

    conn.commit()
