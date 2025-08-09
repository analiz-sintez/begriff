import logging
from dataclasses import dataclass

from nachricht.auth import User
from nachricht.messenger import Context, Emoji
from nachricht.bus import Signal
from nachricht.llm import query_llm
from nachricht.i18n import TranslatableString as _

from .. import router, bus
from ..notes import (
    Language,
    get_native_language,
    get_studied_language,
)
from ..srs import format_explanation


logger = logging.getLogger(__name__)


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


@router.message("^\?\?$")
@router.authorize()
async def _help_on_clarify_text(ctx: Context, user: User) -> None:
    await ctx.send_message(
        _(
            """
📌 Need help with a tricky phrase or word form?
Just send me something that looks confusing — like an unfamiliar article, a weird word ending, or a phrase that doesn’t make sense — and I’ll explain what’s going on.

🔍 *Example:* You're learning German and come across the phrase der Schule, but you know “school” is feminine — “die Schule”. What gives?

*You:* `?? der Schule`
*Me:*
The phrase "der Schule" is in the dative case, singular form of the feminine noun "die Schule" (the school).

Case comparison:

- die Schule — nominative (used as the subject)
- der Schule — dative (used as the indirect object, or "to/for the school")

💬 Example usage:
Ich gehe zur Schule. (I go to school.)
Here, "zur" = "zu der" (to the), and "zu" triggers the dative case.

✅ So, "der" is the dative article for feminine nouns like Schule.
"""
        )
    )


@router.message("^\?\?(?P<text>.+)$")
@router.authorize()
async def _clarify_text(ctx: Context, user: User, text: str) -> None:
    studied_language = get_studied_language(user)
    native_language = get_native_language(user)
    bus.emit(
        ClarificationRequested(
            user_id=user.id,
            language_id=studied_language.id,
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

Keep the tone terse and structural. Don't say "Great question!" or add "Feel free to ask ..." since it does not add to the answer.
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
    language = Language.from_id(language_id)
    native_language = Language.from_id(native_language_id)

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
            Emoji.THUMBSDOWN: ClarificationRequested(
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
