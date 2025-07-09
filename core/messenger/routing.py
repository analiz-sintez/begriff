import re
import logging
from dataclasses import dataclass
from functools import wraps
from inspect import signature, Signature, Parameter
from typing import (
    Optional,
    Callable,
    Union,
    Dict,
    Any,
    TypeAlias,
    TypeVar,
    ParamSpec,
    Concatenate,
)

from .context import Context
from ..auth import get_user, User

P = ParamSpec("P")
R = TypeVar("R")

UserInjector: TypeAlias = Callable[
    [Callable[Concatenate[User, P], R]], Callable[Concatenate[Context, P], R]
]


logger = logging.getLogger(__name__)

Conditions: TypeAlias = Dict[str, Union[str, int]]


def check_conditions(
    conditions: Optional[Conditions], message_context: Optional[Dict]
) -> bool:
    """
    Check handler conditions against given message context.
    """
    if not conditions:
        return True
    if not message_context:
        return False
    match = False
    for condition, value in conditions.items():
        if condition not in message_context:
            continue
        if value is not Any and message_context[condition] != value:
            continue
        match = True
        break
    return match


@dataclass
class Handler:
    """A generic handler."""

    fn: Callable
    message_context: Optional[Conditions]


@dataclass
class Command(Handler):
    """A generic definition for a command handler."""

    name: str
    args: list[str]
    description: str


@dataclass
class MessageHandler(Handler):
    """A generic definition for a message handler."""

    pattern: Union[str, re.Pattern, Callable]


@dataclass
class ReactionHandler(Handler):
    """A generic definition for a reaction handler."""

    emojis: list[str]


@dataclass
class CallbackHandler(Handler):
    """A generic definition for a callback query handler."""

    pattern: str


class Router:
    """
    This class implements Flask-like routing decorators for a bot.

    It is messenger-agnostic and gathers handlers in a declarative form,
    which can then be attached to a specific messenger implementation.
    """

    def __init__(self, config: Optional[object] = None):
        self.config = config
        self.command_handlers: list[Command] = []
        self.callback_query_handlers: list[CallbackHandler] = []
        self.reaction_handlers: list[ReactionHandler] = []
        self.message_handlers: list[MessageHandler] = []

    def command(
        self,
        name: str,
        args: list[str] = [],
        description: Optional[str] = None,
        message_context: Optional[Conditions] = None,
    ) -> Callable:
        """
        A decorator to register a command handler.
        """
        if not description:
            description = name

        def decorator(fn: Callable) -> Callable:
            logger.debug(f"Registering command: /{name}: {description}")
            handler_def = Command(
                fn=fn,
                name=name,
                args=args,
                description=description,
                message_context=message_context,
            )
            self.command_handlers.append(handler_def)
            return fn

        return decorator

    def callback_query(self, pattern: str) -> Callable:
        """
        A decorator to register a callback query handler based on a regex pattern.
        """

        def decorator(fn: Callable) -> Callable:
            logger.debug(f"Registering callback query with pattern: {pattern}")
            handler_def = CallbackHandler(
                fn=fn, pattern=pattern, message_context=None
            )
            self.callback_query_handlers.append(handler_def)
            return fn

        return decorator

    def reaction(
        self,
        emojis: list[str] = [],
        message_context: Optional[Conditions] = None,
    ) -> Callable:
        """
        A decorator to register a reaction handler based on reactions list.
        """

        def decorator(fn: Callable) -> Callable:
            logger.debug(f"Registering reaction handler for emojis: {emojis}")
            handler_def = ReactionHandler(
                fn=fn, emojis=emojis, message_context=message_context
            )
            self.reaction_handlers.append(handler_def)
            return fn

        return decorator

    def message(self, pattern: Union[str, re.Pattern, Callable]) -> Callable:
        """
        A decorator to register a message handler based on a regex pattern or a filter function.
        """

        def decorator(fn: Callable) -> Callable:
            logger.debug(f"Registering message with pattern: {pattern}")
            handler_def = MessageHandler(
                fn=fn, pattern=pattern, message_context=None
            )
            self.message_handlers.append(handler_def)
            return fn

        return decorator

    def _check_conditions(self, conditions: Conditions, ctx: Context):
        # TODO this should not rely on any messenger specifics,
        # this it should be implemented here.
        raise NotImplementedError()

    def authorize(self, admin=False) -> UserInjector:
        def _authorize(
            fn: Callable[Concatenate[User, P], R],
        ) -> Callable[Concatenate[Context, P], R]:
            """
            Get a user from telegram update object.
            The inner function should have `user: User` as the first argument,
            but it will not be propagated to the wrapped function (e.g. after
            this decorator, the outer fn will not have `user` arg. In other words,
            `authorize` injects this argument.)
            """
            sig = signature(fn)

            # We require update object, take user info from it,
            # and inject it into the decorated function, so that
            # it doesn't need to bother.
            # TODO config-based authentication.
            @wraps(fn)
            async def wrapped(ctx: Context, **kwargs):
                if not (user := get_user(ctx.username())):
                    raise Exception("Unauthorized.")
                # Authorize the user.
                allowed_logins = self.config.AUTHENTICATION["allowed_logins"]
                if allowed_logins and user.login not in allowed_logins:
                    raise Exception("Not allowed.")
                if user.login in self.config.AUTHENTICATION["blocked_logins"]:
                    raise Exception("Blocked.")
                if admin:
                    admin_logins = self.config.AUTHENTICATION["admin_logins"]
                    if user.login not in admin_logins:
                        raise Exception("Only admins allowed.")
                # Inject a user into function.
                kwargs["ctx"] = ctx
                kwargs["user"] = user
                new_kwargs = {
                    p.name: kwargs[p.name]
                    for p in sig.parameters.values()
                    if p.name in kwargs
                }
                return await fn(**new_kwargs)

            # Assemble a new signature (bus counts on this info to decide
            # which params to inject)
            params = [p for p in sig.parameters.values()]
            if "ctx" not in {p.name for p in params}:
                params.append(
                    Parameter(
                        "ctx",
                        Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=Context,
                    )
                )
            new_sig = Signature(params)
            wrapped.__signature__ = new_sig
            return wrapped

        return _authorize
