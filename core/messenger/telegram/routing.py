import re
import logging
from inspect import getmodule
from typing import (
    Type,
    Callable,
    Optional,
    get_type_hints,
    Optional,
    get_type_hints,
)

from telegram import BotCommand, Message, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler as PTBCallbackQueryHandler,
    CommandHandler as PTBCommandHandler,
    MessageHandler as PTBMessageHandler,
    MessageReactionHandler as PTBReactionHandler,
    CallbackContext,
    filters,
)

from ...bus import Bus, Signal, unoption, decode, make_regexp
from ..routing import (
    CallbackHandler,
    Command,
    MessageHandler,
    ReactionHandler,
    Router,
)
from .context import TelegramContext

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


def _coerce(arg: str, hint):
    """Coerce a string argument to function type hint."""
    # Get the actual type.
    hint = unoption(hint)
    # Coerce arg to that if we can.
    if hint not in [int, float, str]:
        logger.debug(
            f"type({arg}) is {hint}, can't convert to that. "
            f"Passing as string."
        )
        return arg
    try:
        coerced = hint(arg)
    except (ValueError, TypeError):
        logger.warning(
            f"Could not coerce argument '{arg}' to {hint} "
            f"for command. Passing as string."
        )
        coerced = arg
    return coerced


def _wrap_fn_with_args(fn: Callable, router: Router) -> Callable:
    """
    A helper function to wrap the handler function
    and extract named groups from regex matches for its arguments, coercing types.
    """
    type_hints = get_type_hints(fn)

    async def wrapped(update, context):
        kwargs = {}
        if context.matches:
            match = context.matches[0]
            if isinstance(match, re.Match):
                kwargs.update(match.groupdict())
            elif isinstance(match, dict):
                kwargs.update(match)

        for key, value in kwargs.items():
            if key in type_hints:
                kwargs[key] = _coerce(value, type_hints[key])

        logger.info(f"Calling {fn.__name__} with args: {kwargs}")
        ctx = TelegramContext(update, context, config=router.config)
        return await fn(ctx=ctx, **kwargs)

    return wrapped


def _wrap_command_fn(
    fn: Callable, arg_names: list[str], router: Router
) -> Callable:
    """
    A helper function to wrap a command handler, parsing and coercing
    positional arguments from the message.
    """
    type_hints = get_type_hints(fn)

    async def wrapped(update, context):
        args = context.args if hasattr(context, "args") else []
        kwargs = {name: None for name in arg_names}

        for value, key in zip(args, arg_names[: len(args)]):
            if key in type_hints:
                kwargs[key] = _coerce(value, type_hints[key])

        logger.debug(f"Calling {fn.__name__} with args: {kwargs}")
        ctx = TelegramContext(update, context, config=router.config)
        return await fn(ctx, **kwargs)

    return wrapped


def _create_command_handler(
    command: Command, router: Router
) -> PTBCommandHandler:
    """Creates a telegram.ext.CommandHandler from a Command dataclass."""
    wrapped_fn = _wrap_command_fn(command.fn, command.args, router)
    return PTBCommandHandler(command.name, wrapped_fn)


def _create_callback_query_handler(
    handler: CallbackHandler,
    router: Router,
) -> PTBCallbackQueryHandler:
    """Creates a telegram.ext.CallbackQueryHandler from a CallbackHandler dataclass."""
    wrapped_handler = _wrap_fn_with_args(handler.fn, router)
    return PTBCallbackQueryHandler(wrapped_handler, pattern=handler.pattern)


def _create_reaction_handlers(
    handlers: list[ReactionHandler],
    router: Router,
) -> PTBReactionHandler:
    """
    Creates a telegram.ext.MessageReactionHandler for a bunch of
    ReactionHandler dataclasses.
    """
    # build a dict of emojis to handlers
    emoji_map = {}
    for handler in handlers:
        for emoji in handler.emojis:
            if emoji not in emoji_map:
                emoji_map[emoji] = []
            emoji_map[emoji].append(
                _wrap_fn_with_args(handler.fn, router=router)
            )

    async def dispatch(update, context):
        reaction_obj = update.message_reaction
        emoji = None
        if hasattr(reaction_obj, "new_reaction"):
            reactions = reaction_obj.new_reaction
            if len(reactions) == 1 and hasattr(reactions[0], "emoji"):
                emoji = reactions[0].emoji
        logger.info(f"Got emoji: {emoji}")
        for fn in emoji_map.get(emoji, []):
            await fn(update, context)

    return PTBReactionHandler(dispatch)


def _create_message_handler(
    message_handler: MessageHandler,
    router: Router,
) -> PTBMessageHandler:
    """Creates a telegram.ext.MessageHandler from a MessageHandler dataclass."""
    pattern = message_handler.pattern
    if isinstance(pattern, str) or isinstance(pattern, re.Pattern):
        pattern_filter = filters.Regex(pattern)
    elif callable(pattern):
        pattern_filter = Lambda(pattern)
    else:
        raise ValueError("Pattern must be a regexp or a callable.")

    wrapped_handler = _wrap_fn_with_args(message_handler.fn, router)
    combined_filters = filters.TEXT & ~filters.COMMAND & pattern_filter
    return PTBMessageHandler(combined_filters, wrapped_handler)


def attach_router(router: Router, application: Application):
    """
    Attach the stored handlers from a generic Router to the Telegram application.
    """
    logger.info("Attaching handlers to the application.")

    # Process and add command handlers
    for command in router.command_handlers:
        handler = _create_command_handler(command, router)
        application.add_handler(handler)
        logger.info(f"Command handler added for '/{command.name}'")

    # Process and add callback query handlers
    for callback_handler in router.callback_query_handlers:
        handler = _create_callback_query_handler(callback_handler, router)
        application.add_handler(handler)
        logger.info(
            f"Callback query handler added for pattern: {callback_handler.pattern}"
        )

    # Process and add message handlers
    for message_handler in router.message_handlers:
        handler = _create_message_handler(message_handler, router)
        application.add_handler(handler)
        logger.info(
            f"Message handler added for pattern: {message_handler.pattern}"
        )

    # Set all commands with their descriptions for the bot menu
    bot_commands = [
        BotCommand(cmd.name, cmd.description or cmd.name)
        for cmd in router.command_handlers
        if cmd.description is not None
    ]

    async def set_commands(application: Application):
        await application.bot.set_my_commands(bot_commands)

    if bot_commands:
        application.post_init = set_commands
        logger.info("Bot command descriptions set: %s", bot_commands)

    # Set up a reactions handler.
    # This is a special case. PTB doesn't support dispatching on emoji types,
    # so we register a single handler which does this dispatch.
    if router.reaction_handlers:
        application.add_handler(
            _create_reaction_handlers(router.reaction_handlers, router)
        )


def attach_bus(bus: Bus, application: Application):
    """
    Attach the signals from a Bus to the Telegram application.
    """

    def make_handler(signal_type: Type[Signal]) -> PTBCallbackQueryHandler:
        signal_name = signal_type.__name__

        async def decode_and_emit(update: Update, context: CallbackContext):
            data = update.callback_query.data
            logger.info(f"Got callback: {data}, decoding as {signal_name}.")
            signal = decode(signal_type, data)
            if not signal:
                logger.info(f"Decoding {signal_name} failed.")
                return
            ctx = TelegramContext(update, context, config=bus.config)
            await bus.emit_and_wait(signal, ctx=ctx)

        pattern = make_regexp(signal_type)
        logger.info(f"Registering handler: {pattern} -> {signal_name}")
        handler = PTBCallbackQueryHandler(decode_and_emit, pattern=pattern)
        return handler

    logging.info("Bus: registering signal handlers.")
    for signal_type in bus.signals():
        module_name = getmodule(signal_type).__name__
        signal_name = signal_type.__name__
        logging.info(
            f"Bus: registering a handler for {module_name}.{signal_name}."
        )
        application.add_handler(make_handler(signal_type))
    logging.info("Bus: all signals registered.")
