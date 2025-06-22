from inspect import getmodule
import logging

from telegram.ext import Application, CallbackQueryHandler

# Those are required since routes are declared there.
from . import recap, note, study, note_list, language, onboarding
from .router import router
from ..ui import bus, decode, make_regexp


logger = logging.getLogger(__name__)


def create_bot(token: str) -> Application:
    """
    Create and configure the Telegram bot application
    with command and callback handlers.

    Args:
        token: The bot token for authentication.

    Returns:
        A configured Application instance representing the bot.
    """
    application = Application.builder().token(token).build()
    router.attach(application)

    # For each signal type, register a handler:
    # if signal pattern matches, emit it, triggering all slots to run.
    def make_handler(signal_type):
        signal_name = signal_type.__name__

        async def decode_and_emit(update, context):
            data = update.callback_query.data
            logger.info(f"Got callback: {data}, decoding as {signal_name}.")
            signal = decode(signal_type, data)
            if not signal:
                logger.info(f"Decoding {signal_name} failed.")
                return
            await bus.emit_and_wait(signal, update=update, context=context)

        pattern = make_regexp(signal_type)
        logger.info(f"Registering handler: {pattern} -> {signal_name}")
        handler = CallbackQueryHandler(decode_and_emit, pattern=pattern)
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

    return application
