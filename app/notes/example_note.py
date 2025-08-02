import logging
from .note import Note

logger = logging.getLogger(__name__)


class ExampleNote(Note):
    __mapper_args__ = {
        "polymorphic_identity": "example_note",
    }
