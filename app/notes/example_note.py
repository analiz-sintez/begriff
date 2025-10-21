from typing import Optional

from .note import Note
from .link import Link


class ExampleNote(Note):
    __mapper_args__ = {
        "polymorphic_identity": "example_note",
    }

    def get_topic(self) -> Optional[str]:
        return self.get_option("topic")

    def set_topic(self, topic: str):
        self.set_option("topic", topic)


class ExampleLink(Link):
    __mapper_args__ = {
        "polymorphic_identity": "example_link",
    }
