import logging
from typing import Optional
from nachricht.messenger import Context
from .note import Note
from .language import get_native_language
from ..llm import translate

logger = logging.getLogger(__name__)


class WordNote(Note):
    __mapper_args__ = {
        "polymorphic_identity": "word_note",
    }

    async def get_display_text(self) -> Optional[str]:
        studied_language = self.language
        native_language = get_native_language(self.user)

        # If studied language is the native language, no translation needed.
        if native_language.id == studied_language.id:
            return self.field2

        # Check cache in note options
        translation_key = f"translations/{native_language.code}"
        if translation := self.get_option(translation_key, ""):
            logger.debug(
                f"Found cached translation for note {self.id} to native language {native_language.name}."
            )
            return translation

        logger.info(
            f"Translating note {self.id} from {studied_language.name} to {native_language.name}."
        )
        try:
            translation = await translate(
                self.field1,
                src_language=studied_language.name,
                dst_language=native_language.name,
            )
            self.set_option(translation_key, translation)
            logger.info(
                f"Saved new translation for note {self.id} to native language {native_language.name}."
            )
            return translation
        except Exception as e:
            logger.error(
                f"Error translating note {self.id}: {e}. Returning an explanation."
            )
            return self.field2
