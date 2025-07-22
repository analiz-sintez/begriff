import re
import logging
from typing import List, Optional
from dataclasses import dataclass

from core.auth import User
from core.messenger import Context
from core.bus import Signal
from core.i18n import TranslatableString

from .. import router, bus
from ..srs import get_language
from ..config import Config
from ..llm import get_recap, translate
from .note import get_notes_to_inject


logger = logging.getLogger(__name__)


################################################################
# Recaps
@dataclass
class RecapRequested(Signal):
    """User sent an url and wants a short recap using words."""

    user_id: int
    language_id: int
    url: str


@dataclass
class RecapSent(Signal):
    user_id: int
    language_id: int
    url: str


@router.message(re.compile(r"(?P<url>https?://\S+)$", re.MULTILINE))
@router.authorize()
async def recap_url(ctx: Context, user: User, url: str) -> None:
    language = get_language(
        user.get_option(
            "studied_language", Config.LANGUAGE["defaults"]["study"]
        )
    )
    bus.emit(RecapRequested(user.id, language.id, url))

    notes_to_inject = []
    if "recap" in Config.LLM["inject_notes"]:
        notes_to_inject = get_notes_to_inject(user, language)

    try:
        recap = await get_recap(url, language.name, notes=notes_to_inject)
        response = f"{recap} [(source)]({url})"
    except Exception as e:
        logging.error(f"Got error while recapping: {e}")
        response = _("Couldn't process page, possibly it's too large.")

    await ctx.send_message(
        text=response,
        reply_to=ctx.message,
    )
    bus.emit(RecapSent(user.id, language.id, url))


################################################################
# Translations
@dataclass
class TranslationRequested(Signal):
    """User sent an url and wants a short recap using words."""

    user_id: int
    language_id: int
    text: str


@dataclass
class TranslationSent(Signal):
    user_id: int
    language_id: int
    text: str


@router.message("^!(?P<text>.*)$")
@router.authorize()
async def translate_phrase(ctx: Context, user: User, text: str) -> None:
    defaults = ctx.config.LANGUAGE["defaults"]
    language = get_language(
        user.get_option("studied_language", defaults["study"])
    )
    native_language = get_language(
        user.get_option("native_language", defaults["native"])
    )
    bus.emit(TranslationRequested(user.id, language.id, text))

    try:
        translation = await translate(
            text, src_language=native_language.name, dst_language=language.name
        )
        response = f"{text}\n\n{translation}"
    except Exception as e:
        logging.error(f"Got error while translating: {e}")
        response = _("Couldn't translate, sorry.")

    await ctx.send_message(
        text=response,
        reply_to=ctx.message,
    )
    bus.emit(TranslationSent(user.id, language.id, text))
