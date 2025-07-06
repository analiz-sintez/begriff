import logging
from telegram.ext import Application

# Those are required since routes are declared there.
from . import recap, note, study, note_list, language, onboarding
from ..messenger import router
from ..messenger.telegram import attach_router, attach_bus
from ..bus import bus


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
    attach_router(router, application)
    attach_bus(bus, application)
    return application
