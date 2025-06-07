import re
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram import BotCommand

logger = logging.getLogger(__name__)


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

    def command(self, command: str, description: str = ""):
        """
        A decorator for Telegram commands.

        A command is a regexp which should be applied for the command.
        If it contains named groups, they become parameters for the
        wrapped function.

        Args:
            command: The command name.
            description: Description of the command for application menu.
        """

        def decorator(fn):
            logger.info(
                f"Decorating command: {command} with description: {description}"
            )
            self.command_descriptions[command] = description
            handler = CommandHandler(command, self._wrap_fn_with_args(fn))
            self.command_handlers.append(handler)
            return fn

        return decorator

    def callback_query(self, pattern):
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

    def message(self, pattern):
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
                pattern_filter = filters.create(pattern)
            else:
                raise ValueError("Pattern must be a regexp or a callable.")

            handler = MessageHandler(
                filters.TEXT & ~filters.COMMAND & pattern_filter,
                self._wrap_fn_with_args(fn),
            )
            self.message_handlers.append(handler)
            return fn

        return decorator

    def _wrap_fn_with_args(self, fn):
        """
        A helper function to wrap the handler function
        and extract named groups for its arguments.
        """

        def wrapped(update, context):
            logger.debug(
                f"Calling function {fn.__name__} "
                f"with update: {update} and context: {context}"
            )
            match = context.matches[0] if context.matches else None
            if match:
                kwargs = match.groupdict()
                logger.info(
                    f"Function {fn.__name__} called with args: {kwargs}"
                )
                return fn(update, context, **kwargs)
            else:
                logger.info(f"Function {fn.__name__} called with no args.")
                return fn(update, context)

        return wrapped


router = Router()
