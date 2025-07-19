import re
import logging
from functools import wraps
from inspect import getmodule
from typing import (
    Dict,
    Type,
    Callable,
    Optional,
    Any,
    List,
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
    check_conditions,
    CallbackHandler,
    Command,
    MessageHandler,
    ReactionHandler,
    Router,
    Conditions,
)
from .context import TelegramContext

logger = logging.getLogger(__name__)


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

    async def wrapped(update: Update, context: TelegramContext, **kwargs):
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

    logger.warning(f"Wrapping function: {wrapped.__name__}")
    return wrapped


def _wrap_command_fn(
    fn: Callable, arg_names: list[str], router: Router
) -> Callable:
    """
    A helper function to wrap a command handler, parsing and coercing
    positional arguments from the message.
    """
    type_hints = get_type_hints(fn)

    @wraps(fn)
    async def wrapped(update, context, **outer_kwargs):
        args = context.args if hasattr(context, "args") else []
        arg_cnt = min(len(args), len(arg_names))
        for value, key in zip(args[:arg_cnt], arg_names[:arg_cnt]):
            if key in type_hints:
                outer_kwargs[key] = _coerce(value, type_hints[key])
        kwargs = {
            key: outer_kwargs[key]
            for key in type_hints.keys()
            if key in outer_kwargs
        }

        logger.debug(f"Calling {fn.__name__} with args: {outer_kwargs}")
        ctx = TelegramContext(update, context, config=router.config)
        return await fn(ctx, **kwargs)

    return wrapped


def _create_command_handler(
    name: str, handlers: List[Command], router: Router
) -> PTBCommandHandler:
    """
    Creates a *single* telegram.CommandHandler for a bunch of
    CommandHandler dataclasses.
    They may have different conditions, e.g. on message context.

    """
    # TODO: this logic is too primitive. Maybe we should have
    # `is_final` property which terminates the search.
    # Or sort handlers based on conditions count, search from the ones with
    # many conditions first, and terminate the search if we found something.
    conditional_handlers = []
    conditionless_handlers = []
    for handler in handlers:
        if handler.conditions:
            conditional_handlers.append(handler)
        else:
            conditionless_handlers.append(handler)

    async def dispatch(update, context):
        ctx = TelegramContext(update, context, config=router.config)
        # Get the message replied to.
        message_ctx = None
        if reply_to := update.message.reply_to_message:
            message_ctx = ctx.message_context.get(reply_to.message_id)
        found = False
        for handler in conditional_handlers:
            # Check the message context condition.
            if check_conditions(handler.conditions, message_ctx):
                logger.info(
                    f"Handler matched for command {name}: {handler.conditions}."
                )
                found = True
                await handler.fn(update, context, reply_to=reply_to)
        if found:
            return
        for handler in conditionless_handlers:
            logger.info(f"Calling conditionless handler for command {name}.")
            await handler.fn(update, context, reply_to=reply_to)

    return PTBCommandHandler(name, dispatch)


def _create_callback_query_handler(
    handler: CallbackHandler,
    router: Router,
) -> PTBCallbackQueryHandler:
    """Creates a telegram.ext.CallbackQueryHandler from a CallbackHandler dataclass."""
    wrapped_handler = _wrap_fn_with_args(handler.fn, router)
    return PTBCallbackQueryHandler(wrapped_handler, pattern=handler.pattern)


def _create_reaction_handlers(
    handlers: List[ReactionHandler],
    router: Router,
) -> PTBReactionHandler:
    """
    Creates a *single* telegram.ext.MessageReactionHandler for a bunch of
    ReactionHandler dataclasses.
    """
    # Build a mapping of emojis to handlers
    emoji_map = {}
    for handler in handlers:
        handler.fn = _wrap_fn_with_args(handler.fn, router=router)
        for emoji in handler.emojis:
            if emoji not in emoji_map:
                emoji_map[emoji] = []
            emoji_map[emoji].append(handler)

    async def dispatch(update: Update, context: TelegramContext):
        ctx = TelegramContext(update, context, config=router.config)
        # Get the reply to message.
        reaction_obj = update.message_reaction
        chat = reaction_obj.chat
        date = reaction_obj.date
        message_id = reaction_obj.message_id
        message_ctx = ctx.message_context.get(message_id)
        message = Message(message_id=message_id, chat=chat, date=date)
        emoji = None
        if hasattr(reaction_obj, "new_reaction"):
            reactions = reaction_obj.new_reaction
            if len(reactions) == 1 and hasattr(reactions[0], "emoji"):
                emoji = reactions[0].emoji
        logger.info(f"Got emoji: {emoji}")
        for handler in emoji_map.get(emoji, []):
            # Check the message context condition.
            if check_conditions(handler.conditions, message_ctx):
                # TODO this should not await, just shoot and forget
                logger.info(
                    f"Handler matched for emoji {emoji}: {handler.conditions}."
                )
                await handler.fn(
                    update, context, emoji=emoji, reply_to=message
                )

    return PTBReactionHandler(dispatch)


class LambdaFilter(filters.MessageFilter):
    """
    A function filter: applies a function to message text
    and returns either bool or a dict with fetched arguments for
    a handler.
    """

    __slots__ = ("fn",)

    def __init__(self, fn: Callable):
        self.fn: Callable = fn
        super().__init__(
            name=f"filters.LambdaFilter({self.fn})", data_filter=True
        )

    def filter(
        self, message: Message
    ) -> Optional[dict[str, list[re.Match[str]]]]:
        if message.text and (match := self.fn(message.text)):
            return {"matches": [match]}
        return {}


def _create_message_handlers(
    message_handlers: List[MessageHandler],
    router: Router,
) -> PTBMessageHandler:
    """
    Combile all MessageHandlers and register them
    as onr telegram.ext.MessageHandler.
    """
    # Preprocess message handelrs:
    for handler in message_handlers:
        # ... wrap the function
        handler.fn = _wrap_fn_with_args(handler.fn, router)
        # ... prepare the pattern
        pattern = handler.pattern
        if isinstance(pattern, str) or isinstance(pattern, re.Pattern):
            pattern_filter = filters.Regex(pattern)
        elif callable(pattern):
            pattern_filter = LambdaFilter(pattern)
        else:
            raise ValueError("Pattern must be a regexp or a callable.")
        handler.pattern = pattern_filter
        logger.info("Message handler added for %s.", handler.fn.__name__)

    async def dispatch(update: Update, context: TelegramContext):
        ctx = TelegramContext(update, context, config=router.config)
        message = update.message
        # Here we can do the trick: get the one-time reply-to message id
        # for the user and clear this id right after that.
        parent_ctx = None
        if parent := message.reply_to_message:
            parent_ctx = ctx.message_context.get(parent.message_id)
        # For each handler, check conditions and call if they are met.
        for handler in message_handlers:
            if not (matches := handler.pattern.filter(message)):
                continue
            if not check_conditions(handler.conditions, parent_ctx):
                continue
            # TODO: log wrapped function name instead of conditions
            logger.info(f"Message handler matched: %s", handler.conditions)
            await handler.fn(update, context, **matches)

    combined_filters = filters.TEXT & ~filters.COMMAND & pattern_filter
    return PTBMessageHandler(combined_filters, dispatch)


def attach_router(router: Router, application: Application):
    """
    Attach the stored handlers from a generic Router to the Telegram application.
    """
    logger.info("Attaching handlers to the application.")

    # Process and add command handlers
    # For each command gather all registered handlers.
    command_map = {}
    for handler in router.command_handlers:
        if handler.name not in command_map:
            command_map[handler.name] = []
        handler.fn = _wrap_command_fn(handler.fn, handler.args, router)
        command_map[handler.name].append(handler)

    for command_name, handlers in command_map.items():
        handler = _create_command_handler(command_name, handlers, router)
        application.add_handler(handler)
        logger.debug(f"Command handler added for '/{command_name}'")

    # Process and add callback query handlers
    for callback_handler in router.callback_query_handlers:
        handler = _create_callback_query_handler(callback_handler, router)
        application.add_handler(handler)
        logger.debug(
            f"Callback query handler added for pattern: {callback_handler.pattern}"
        )

    # Process and add message handlers
    # register them all at once to avoid "only first matched is called" rule
    handler = _create_message_handlers(router.message_handlers, router)
    application.add_handler(handler)
    logger.debug(f"Message handlers added.")

    # Set all commands with their descriptions for the bot menu
    # TODO resolve translatable strings
    bot_commands = [
        BotCommand(cmd.name, str(cmd.description or cmd.name))
        for cmd in router.command_handlers
    ]

    async def set_commands(application: Application):
        await application.bot.set_my_commands(bot_commands)

    if bot_commands:
        application.post_init = set_commands
        logger.debug("Bot command descriptions set: %s", bot_commands)

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
            logger.debug(f"Got callback: {data}, decoding as {signal_name}.")
            signal = decode(signal_type, data)
            if not signal:
                logger.warning(f"Decoding {signal_name} failed.")
                return
            ctx = TelegramContext(update, context, config=bus.config)
            await bus.emit_and_wait(signal, ctx=ctx)

        pattern = make_regexp(signal_type)
        logger.debug(f"Registering handler: {pattern} -> {signal_name}")
        handler = PTBCallbackQueryHandler(decode_and_emit, pattern=pattern)
        return handler

    logging.info("Bus: registering signal handlers.")
    for signal_type in bus.signals():
        module_name = getmodule(signal_type).__name__
        signal_name = signal_type.__name__
        logging.debug(
            f"Bus: registering a handler for {module_name}.{signal_name}."
        )
        application.add_handler(make_handler(signal_type))
    logging.info("Bus: all signals registered.")
