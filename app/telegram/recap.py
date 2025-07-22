import re
import logging
from dataclasses import dataclass

from app.srs.service import get_note
from core.auth import User
from core.messenger import Context
from core.bus import Signal
from core.llm import query_llm
from core.i18n import TranslatableString as _

from .. import router, bus
from ..srs import get_language, get_note, Note
from ..config import Config
from ..llm import get_recap, translate
from .note import get_notes_to_inject, format_explanation


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


@router.message("^!!(?P<text>.*)$")
@router.authorize()
async def _translate_phrase(ctx: Context, user: User, text: str) -> None:
    defaults = ctx.config.LANGUAGE["defaults"]
    language = get_language(
        user.get_option("studied_language", defaults["study"])
    )
    bus.emit(TranslationRequested(user.id, language.id, text), ctx=ctx)


@bus.on(TranslationRequested)
@router.authorize()
async def translate_phrase(
    ctx: Context, user: User, language_id: int, text: str
) -> None:
    defaults = ctx.config.LANGUAGE["defaults"]
    language = get_language(language_id)
    native_language = get_language(
        user.get_option("native_language", defaults["native"])
    )

    try:
        translation = await translate(
            text, src_language=native_language.name, dst_language=language.name
        )
        response = f"{translation}"
    except Exception as e:
        logging.error(f"Got error while translating: {e}")
        response = _("Couldn't translate, sorry.")

    await ctx.send_message(
        text=response,
        reply_to=ctx.message,
        on_reaction={"👎": TranslationRequested(user.id, language.id, text)},
    )
    bus.emit(TranslationSent(user.id, language.id, text))


################################################################
# Clarification
@dataclass
class ClarificationRequested(Signal):
    """User sent a piece of language and asks what the hell is happening in it."""

    user_id: int
    language_id: int
    native_language_id: int
    text: str


@dataclass
class ClarificationSent(Signal):
    user_id: int
    language_id: int
    native_language_id: int
    text: str


@router.message("^\?\?(?P<text>.*)$")
@router.authorize()
async def _clarify_text(ctx: Context, user: User, text: str) -> None:
    defaults = ctx.config.LANGUAGE["defaults"]
    language = get_language(
        user.get_option("studied_language", defaults["study"])
    )
    native_language = get_language(
        user.get_option("native_language", defaults["native"])
    )
    bus.emit(
        ClarificationRequested(
            user_id=user.id,
            language_id=language.id,
            native_language_id=native_language.id,
            text=text,
        ),
        ctx=ctx,
    )


async def get_clarification(text: str, language: str, native_language: str):
    return await query_llm(
        f"""
You are {language} tutor helping a student to learn new language. Their native language is {native_language}.

You will be given a word or phrase which is tricky for the student. There could be form or word, conjugation, articles or other complexity. Your task is to unravel that and clarify what is happening and how it works. Give a short and clear comment. 
        """,
        text,
    )


@bus.on(ClarificationRequested)
@router.authorize()
async def clarify_text(
    ctx: Context,
    user: User,
    language_id: int,
    native_language_id: int,
    text: str,
) -> None:
    language = get_language(language_id)
    native_language = get_language(native_language_id)

    try:
        translation = await get_clarification(
            text, language=language.name, native_language=native_language.name
        )
        response = format_explanation(translation)
    except Exception as e:
        logging.error(f"Got error while clarifying: {e}")
        response = _("Couldn't clarify, sorry.")

    await ctx.send_message(
        text=response,
        reply_to=ctx.message,
        on_reaction={
            "👎": ClarificationRequested(
                user_id=user.id,
                language_id=language.id,
                native_language_id=native_language.id,
                text=text,
            )
        },
    )
    bus.emit(
        ClarificationSent(
            user_id=user.id,
            language_id=language.id,
            native_language_id=native_language.id,
            text=text,
        )
    )
