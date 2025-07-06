import logging
from dataclasses import dataclass
from typing import (
    List,
    Optional,
)

from ..bus import Signal

logger = logging.getLogger(__name__)


class Message:
    pass


class Context:
    """
    TODO:

    Stores all contextual info, preferably in a messenger-independent
    way. Should support Telegram, Whatsapp, Matrix, Slack, Mattermost,
    maybe even IRC.
    """

    def username(self) -> str:
        raise NotImplementedError()

    async def send_message(
        self,
        text: str,
        markup: Optional[object] = None,
        image: Optional[str] = None,
        new: bool = False,
        reply_to: Optional[Message] = None,
    ):
        raise NotImplementedError()


@dataclass
class Button:
    text: str
    callback: Signal


@dataclass
class Keyboard:
    buttons: List[List[Button]]
