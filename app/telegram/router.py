import re
import logging
from typing import Callable, Optional, get_type_hints, Union
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram import BotCommand, Message
from ..ui import unoption

logger = logging.getLogger(__name__)


class Lambda(filters.MessageFilter):
    """
    A function filter: applies a function to message text
    and returns either bool or a dict with fetched arguments for
    a handler.
    """

    __slots__ = ("fn",)

    def __init__(self, fn: Callable):
        self.fn: Callable = fn
        super().__init__(name=f"filters.Lambda({self.fn})", data_filter=True)

    def filter(
        self, message: Message
    ) -> Optional[dict[str, list[re.Match[str]]]]:
        if message.text and (match := self.fn(message.text)):
            return {"matches": [match]}
        return {}


class Router:
    """
    This class implements Flask-like routing decorators for Telegram bot.

    While not attached to Telegram application, it is just a singleton
    which stores decorated functions.

    When attached to an application, it adds all functions it decorates
    to this application.

    Idea: https://www.reddit.com/r/learnpython/comments/54gzw7/how_do_you_actually_use_decorators/
    """

    def __init__(self):
        self.command_handlers = []
        self.callback_query_handlers = []
        self.message_handlers = []
        self.command_descriptions = {}

    def attach(self, application: Application):
        """
        Attach the stored handlers to the given application.
        """
        logger.info("Attaching handlers to the application.")
        for handler in self.command_handlers:
            application.add_handler(handler)
            logger.info(f"Command handler added: {handler}")

        for handler in self.callback_query_handlers:
            application.add_handler(handler)
            logger.info(f"Callback query handler added: {handler}")

        for handler in self.message_handlers:
            application.add_handler(handler)
            logger.info(f"Message handler added: {handler}")

        # Set all commands with their descriptions
        commands = [
            BotCommand(command, description)
            for command, description in self.command_descriptions.items()
        ]

        async def set_commands(application):
            await application.bot.set_my_commands(commands)

        application.post_init = set_commands
        logger.info("Commands set with descriptions: %s", commands)

    def _wrap_command_fn(self, fn: Callable, arg_names: list[str]) -> Callable:
        type_hints = get_type_hints(fn)

        def wrapped(update, context):
            args = context.args if hasattr(context, "args") else []
            args_dict = {name: None for name in arg_names}

            for arg, name in zip(args, arg_names[: len(args)]):
                if name not in type_hints:
                    continue
                # ... transform scalar types from type hints
                hint = unoption(type_hints[name])
                if hint in [int, float, str]:
                    args_dict[name] = hint(arg)
                else:
                    args_dict[name] = arg

            logger.debug(
                f"Calling function {fn.__name__} "
                f"with coerced args: {args_dict}"
            )
            return fn(update=update, context=context, **args_dict)

        return wrapped

    def command(
        self,
        command: str,
        args: list[str] = [],
        description: Optional[str] = None,
    ) -> Callable:
        """
        A decorator for Telegram commands.

        Args:
            command: The command name with its expected argument names.
            arg: List of optional sequential arguments.
            description: Description of the command for application menu.
        """
        if not description:
            description = command

        def decorator(fn):
            logger.info(
                f"Decorating command: {command} with description: {description}"
            )
            self.command_descriptions[command] = description
            handler = CommandHandler(command, self._wrap_command_fn(fn, args))
            self.command_handlers.append(handler)
            return fn

        return decorator

    def callback_query(self, pattern: str) -> Callable:
        """
        Adds CallbackQueryHandler to given regexp pattern.
        If it contains named groups, the wrapper function fetches them
        and supplies the wrapped function with them.
        """

        def decorator(fn):
            logger.info(f"Decorating callback query with pattern: {pattern}")
            handler = CallbackQueryHandler(
                self._wrap_fn_with_args(fn), pattern=pattern
            )
            self.callback_query_handlers.append(handler)
            return fn

        return decorator

    def message(self, pattern: Union[str, Callable]) -> Callable:
        """
        Adds MessageHandler with filters.TEXT & ~filters.COMMAND,
        for messages matching the given pattern (can be regexp, possibly
        with named groups which become fn args, or a function returning
        bool if function fits).
        """

        def decorator(fn):
            logger.info(f"Decorating message with pattern: {pattern}")
            if isinstance(pattern, str) or isinstance(pattern, re.Pattern):
                pattern_filter = filters.Regex(pattern)
            elif callable(pattern):
                pattern_filter = Lambda(pattern)
            else:
                raise ValueError("Pattern must be a regexp or a callable.")

            handler = MessageHandler(
                filters.TEXT & ~filters.COMMAND & pattern_filter,
                self._wrap_fn_with_args(fn),
            )
            self.message_handlers.append(handler)
            return fn

        return decorator

    def _wrap_fn_with_args(self, fn: Callable) -> Callable:
        """
        A helper function to wrap the handler function
        and extract named groups for its arguments, coercing types.
        """

        type_hints = get_type_hints(fn)

        def wrapped(update, context):
            logger.debug(
                f"Calling function {fn.__name__} "
                f"with update: {update} and context: {context}"
            )
            # ... look for arguments from regexps
            kwargs = None
            match = context.matches[0] if context.matches else None
            if isinstance(match, re.Match):
                kwargs = match.groupdict()
            elif isinstance(match, dict):
                kwargs = match

            if kwargs:
                # ... use type hints to coerce fetched arguments
                coerced_kwargs = {
                    k: (
                        type_hints.get(k, lambda x: x)(v)
                        if k in type_hints
                        else v
                    )
                    for k, v in kwargs.items()
                }
                logger.info(
                    f"Function {fn.__name__} called with args: {coerced_kwargs}"
                )
                return fn(update=update, context=context, **coerced_kwargs)
            else:
                logger.info(f"Function {fn.__name__} called with no args.")
                return fn(update, context)

        return wrapped


router = Router()
