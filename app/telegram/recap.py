import re
import logging

from core.auth import User
from core.messenger import Context

from .. import router
from ..srs import get_language
from ..config import Config
from ..llm import get_recap
from .note import get_notes_to_inject


logger = logging.getLogger(__name__)


@router.message(re.compile(r"(?P<url>https?://\S+)$", re.MULTILINE))
@router.authorize()
async def recap_url(ctx: Context, user: User, url: str) -> None:
    language = get_language(
        user.get_option(
            "studied_language", Config.LANGUAGE["defaults"]["study"]
        )
    )

    notes_to_inject = None
    if "recap" in Config.LLM["inject_notes"]:
        notes_to_inject = get_notes_to_inject(user, language)

    try:
        recap = await get_recap(url, language.name, notes=notes_to_inject)
        response = f"{recap} [(source)]({url})"
    except Exception as e:
        logging.error(f"Got error while recapping: {e}")
        response = "Couldn't process page, possibly it's too large."

    await ctx.send_message(
        text=response,
        reply_to=ctx.update.message,
    )
