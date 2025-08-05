import logging
from dataclasses import dataclass

from nachricht.auth import User
from nachricht.messenger import Context, Emoji
from nachricht.bus import Signal
from nachricht.i18n import TranslatableString as _

from .. import router, bus
from ..notes import (
    Language,
    get_native_language,
    get_studied_language,
)
from ..llm import translate


logger = logging.getLogger(__name__)


################################################################
# Translations
@dataclass
class TranslationRequested(Signal):
    """User sent a text and wants its translation into the language they study."""

    user_id: int
    src_language_id: int
    dst_language_id: int
    text: str


@dataclass
class TranslationSent(Signal):
    user_id: int
    language_id: int
    text: str


@router.message("^!!$")
@router.authorize()
async def _help_on_translate_phrase(ctx: Context, user: User) -> None:
    await ctx.send_message(
        _(
            """
🌐 Want to say something in your new language?
Just send me a word or phrase from your native language, and I’ll translate it into the one you're studying.
Start your message with !! to get an instant translation.

🧪 *Examples:*
You're learning German and want to say:

*You:* `!! Hello everybody!`
*Me:* Hallo zusammen!

*You:* `!! I’m running late, sorry!`
*Me:* Ich komme zu spät,entschuldige!

*You:* `!! What do you think about it?`
*Me:* Was hältst du davon?
"""
        )
    )


@router.message("^!!(?P<text>.+)$")
@router.authorize()
async def _translate_phrase(ctx: Context, user: User, text: str) -> None:
    studied_language = get_studied_language(user)
    native_language = get_native_language(user)
    bus.emit(
        TranslationRequested(
            user.id,
            src_language_id=native_language.id,
            dst_language_id=studied_language.id,
            text=text,
        ),
        ctx=ctx,
    )


@bus.on(TranslationRequested)
@router.authorize()
async def translate_phrase(
    ctx: Context,
    user: User,
    src_language_id: int,
    dst_language_id: int,
    text: str,
) -> None:
    dst_language = Language.from_id(dst_language_id)
    src_language = Language.from_id(src_language_id)

    translation = await translate(
        text,
        src_language=src_language.name,
        dst_language=dst_language.name,
    )
    response = f"{src_language.flag} {dst_language.flag} {translation}"
    message = await ctx.send_message(
        text=response,
        reply_to=ctx.message,
        on_reaction={
            Emoji.THUMBSDOWN: TranslationRequested(
                user.id, src_language.id, dst_language.id, text
            )
        },
    )
    bus.emit(TranslationSent(user.id, dst_language.id, text))
    return message
