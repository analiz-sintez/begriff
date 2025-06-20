import logging
from dataclasses import asdict

from telegram import Update
from telegram.ext import Application, CallbackContext, CallbackQueryHandler

# Those are required since routes are declared there.
from . import recap, note, study, note_list, language
from .router import router
from ..ui import bus, encode, decode, make_regexp


logger = logging.getLogger(__name__)


@router.command("start", description="Start using the bot")
async def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message to the user when they start the bot.

    Args:
        update: The Telegram update that triggered this function.
        context: The callback context as part of the Telegram framework.
    """
    logger.info("User %s started the bot.", update.effective_user.id)
    await update.message.reply_text(
        """
Welcome to the Begriff Bot! I'll help you learn new words in a foreign language.
        
Here are the commands you can use:
Simply enter words separated by a newline to add them to your study list with automatic explanations.
/list - See all the words you've added to your study list along with their details.
/study - Start a study session with your queued words.
"""
    )


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

    # for each signal, register a handler:
    # if signal pattern matches:
    # ... parse callback data and decode the signal (update.callback_query.data)
    # ... emit it
    # ... where to put context?
    # - should I make a patched bus?
    # - I can store stuff in a signal?
    # - What if router decorates handlers, adding them context and update,
    #   and then gives them to bus? nope,
    # Bus calls and signal processing should be context-dependent!
    # Or... now we have two signalling mechanisms: intra-app and
    # app-vs-user (via tg).
    # - in both, we should get update and context if needed
    #   (or just view_id card_id etc if that's enough)
    # - in extra-app signalling, we should rely on telegram app
    # - in intra-app, we can do everything without tg app
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

    for signal_type in bus.signals():
        application.add_handler(make_handler(signal_type))

    return application
