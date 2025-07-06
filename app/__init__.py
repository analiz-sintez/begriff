import logging
from dataclasses import dataclass
from core.messenger import Router
from core.bus import create_bus, Signal
from .config import Config

router = Router(config=Config)
bus = create_bus(config=Config)

logger = logging.getLogger(__name__)


@dataclass
class EmojiSent(Signal):
    emoji: str


@router.reaction(["❤"])
async def dispatch_reaction(ctx):
    logger.info(f"Got reaction for message: {ctx.update.message}")
    bus.emit(EmojiSent("LOVE! PEACE!"))
