import logging

from typing import Optional
from dataclasses import dataclass

from nachricht.auth import User
from nachricht.bus import Signal
from nachricht.messenger import Context, Emoji
from nachricht.i18n import TranslatableString as _

from .. import bus, router
from ..llm import (
    find_mistakes,
)
from ..notes import (
    get_native_language,
    get_studied_language,
)

logger = logging.getLogger(__name__)


################################################################
# Grammar check


@dataclass
class GrammarCheckRequested(Signal):
    """A user asked to check the phrase or sentence for the grammar errors."""

    user_id: int
    text: str


@dataclass
class GrammarCheckSent(Signal):
    """The user text was checked for the grammar errors and the reply was sent."""

    user_id: int
    text: str


@dataclass
class GrammarCheckDownvoted(Signal):
    """The user disliked the grammar check we sent them."""

    user_id: int
    text: str


@router.command(
    "check", ["text"], description=_("Check a phrase for grammar mistakes")
)
@router.authorize()
async def _check_sentence_for_mistakes(
    ctx: Context,
    user: User,
    text: Optional[str] = None,
):
    if not text:
        return await ctx.send_message(
            _(
                """
Send me a phrase or a sentence, and I'll check it for grammatic or other mistakes.
        """
            )
        )
    bus.emit(GrammarCheckRequested(user.id, text), ctx=ctx)


@bus.on(GrammarCheckRequested)
@router.authorize()
async def check_sentence_for_mistakes(
    ctx: Context,
    user: User,
    text: str,
    explanation: Optional[str] = None,
):
    language = get_studied_language(user)
    native_language = get_native_language(user)

    reply = await find_mistakes(text, language, native_language)
    message = await ctx.send_message(
        reply,
        on_reaction={
            Emoji.THUMBSDOWN: GrammarCheckDownvoted(user.id, text),
            Emoji.PRAY: GrammarCheckRequested(user.id, text),
        },
    )
    bus.emit(GrammarCheckSent(user.id, text), ctx=ctx)
    return message
