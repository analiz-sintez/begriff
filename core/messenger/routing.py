from typing import Callable
from dataclasses import dataclass

import re
import logging
from typing import Callable, Optional, get_type_hints, Union

from ..bus import unoption


logger = logging.getLogger(__name__)


@dataclass
class Command:
    """A generic definition for a command handler."""

    fn: Callable
    name: str
    args: list[str]
    description: str


@dataclass
class MessageHandler:
    """A generic definition for a message handler."""

    fn: Callable
    pattern: Union[str, re.Pattern, Callable]


@dataclass
class CallbackHandler:
    """A generic definition for a callback query handler."""

    fn: Callable
    pattern: str


class Router:
    """
    This class implements Flask-like routing decorators for a bot.

    It is messenger-agnostic and gathers handlers in a declarative form,
    which can then be attached to a specific messenger implementation.
    """

    def __init__(self):
        self.command_handlers: list[Command] = []
        self.callback_query_handlers: list[CallbackHandler] = []
        self.message_handlers: list[MessageHandler] = []

    def command(
        self,
        name: str,
        args: list[str] = [],
        description: Optional[str] = None,
    ) -> Callable:
        """
        A decorator to register a command handler.
        """
        if not description:
            description = name

        def decorator(fn: Callable) -> Callable:
            logger.info(
                f"Decorating command: /{name} with description: {description}"
            )
            handler_def = Command(
                fn=fn,
                name=name,
                args=args,
                description=description,
            )
            self.command_handlers.append(handler_def)
            return fn

        return decorator

    def callback_query(self, pattern: str) -> Callable:
        """
        A decorator to register a callback query handler based on a regex pattern.
        """

        def decorator(fn: Callable) -> Callable:
            logger.info(f"Decorating callback query with pattern: {pattern}")
            handler_def = CallbackHandler(fn=fn, pattern=pattern)
            self.callback_query_handlers.append(handler_def)
            return fn

        return decorator

    def message(self, pattern: Union[str, re.Pattern, Callable]) -> Callable:
        """
        A decorator to register a message handler based on a regex pattern or a filter function.
        """

        def decorator(fn: Callable) -> Callable:
            logger.info(f"Decorating message with pattern: {pattern}")
            handler_def = MessageHandler(fn=fn, pattern=pattern)
            self.message_handlers.append(handler_def)
            return fn

        return decorator


router = Router()
