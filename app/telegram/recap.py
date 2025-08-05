import re
import logging
from dataclasses import dataclass

from nachricht.auth import User
from nachricht.messenger import Context, Emoji
from nachricht.bus import Signal
from nachricht.i18n import TranslatableString as _

from .. import router, bus
from ..notes import (
    get_studied_language,
)
from ..srs import get_notes_to_inject
from ..config import Config
from ..llm import get_recap


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
    language = get_studied_language(user)
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
