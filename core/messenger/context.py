import logging
from typing import Optional, Dict, Union
from dataclasses import dataclass
from typing import (
    List,
    Optional,
)
from babel import Locale

from ..bus import Signal
from ..i18n import TranslatableString

logger = logging.getLogger(__name__)


@dataclass
class User:
    id: int
    login: str
    locale: Locale
    _: Optional[object] = None  # raw object


@dataclass
class Chat:
    id: int
    _: Optional[object]


@dataclass
class Message:
    id: int
    chat_id: int
    user_id: Optional[int] = None
    text: Optional[str] = None
    parent: Optional[object] = None  # another Message object
    # context: Dict
    # messenger: str
    _: Optional[object] = None  # raw object


@dataclass
class Button:
    text: Union[str, TranslatableString]
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
    def user(self) -> User:
        raise NotImplementedError()

    @property
    def message(self) -> Message:
        raise NotImplementedError()

    def context(self, obj: Union[Message, Chat, User]) -> Dict:
        """Return a context dict for a given object."""
        # TODO bad naming?
        raise NotImplementedError()

    async def send_message(
        self,
        text: Union[str, TranslatableString],
        markup: Optional[Keyboard] = None,
        image: Optional[str] = None,
        new: bool = False,
        reply_to: Optional[Message] = None,
        on_reply: Optional[Signal] = None,
        context: Optional[Dict] = None,
    ):
        """
        Arguments:
        new:
          Don't edit the message even if it's possible.
        reply_to:
          A message which to reply.
        on_reply:
          A signal to be emitted if a user replies to this message.
          What counts as reply is determined by each messenger's adaptor.
          Recommended options are:
          - For telegram-like messengers: direct reply with a "reply" mechanics.
          - Also, a message right after the current one, without intermittance by
            a command, and possibly within a given time frame, should count as
            reply.
          - For slack-like messengers: a message in the same thread.

        """
        raise NotImplementedError()
