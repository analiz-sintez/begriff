import logging
from typing import Optional, Dict
from dataclasses import dataclass
from typing import (
    List,
    Optional,
)

from ..bus import Signal

logger = logging.getLogger(__name__)


@dataclass
class Message:
    id: int
    chat_id: int


@dataclass
class Button:
    text: str
    callback: Signal


@dataclass
class Keyboard:
    buttons: List[List[Button]]


class Context:
    """
    TODO:

    Stores all contextual info, preferably in a messenger-independent
    way. Should support Telegram, Whatsapp, Matrix, Slack, Mattermost,
    maybe even IRC.
    """

    def __init__(self, config: Optional[object] = None):
        self.config = config

    def username(self) -> str:
        raise NotImplementedError()

    @property
    def message_map(self) -> Dict[int, Dict]:
        """
        A store of per-message metadata. e.g. a note bound to the message
        to perform context actions on it.
        """
        raise NotImplementedError()

    async def send_message(
        self,
        text: str,
        markup: Optional[Keyboard] = None,
        image: Optional[str] = None,
        new: bool = False,
        reply_to: Optional[Message] = None,
    ):
        raise NotImplementedError()
