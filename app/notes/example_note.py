import logging

from ..llm import translate
from .language import get_native_language
from .link import Link
from .note import Note


logger = logging.getLogger(__name__)


class ExampleNote(Note):
    __mapper_args__ = {
        "polymorphic_identity": "example_note",
    }

    async def get_display_text(self, translate: bool = True) -> str:
        # field1: example sentence (in studied language)
        # field2: topic (in studied language)
        if not self.field2:
            return self.field1

        native_language = get_native_language(self.user)
        studied_language = self.language

        # If native language is same as studied, no translation needed.
        if not translate or (native_language.id == studied_language.id):
            return f"[{self.field2}] {self.field1}"

        # Check for cached translation
        translation_key = f"translations/topic/{native_language.code}"
        if translated_topic := self.get_option(translation_key):
            return f"[{translated_topic}] {self.field1}"

        # Translate the topic
        try:
            translated_topic = await translate(
                self.field2,
                src_language=studied_language,
                dst_language=native_language,
            )
            self.set_option(translation_key, translated_topic)
        except Exception as e:
            logger.error(
                f"Could not translate example topic '{self.field2}': {e}"
            )
            # Fallback to topic in studied language
            translated_topic = self.field2

        return f"[{translated_topic}] {self.field1}"

    def get_word(self) -> Note:
        link = ExampleLink.query.filter_by(to_id=self.id).first()
        return link.note_from


class ExampleLink(Link):
    __mapper_args__ = {
        "polymorphic_identity": "example_link",
    }


def examples_for(note: Note):
    example_links = ExampleLink.query.filter_by(from_id=note.id).all()
    example_notes = [
        ExampleNote.query.filter_by(id=link.to_id).first()
        for link in example_links
    ]
    return example_notes
