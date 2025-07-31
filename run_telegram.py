import logging

from telegram import Update
from telegram.ext import Application

from nachricht import setup_logging

setup_logging()

from nachricht.bus import Bus
from nachricht.messenger import Router
from nachricht.messenger.telegram import attach_bus, attach_router

from app import bus, router, create_app, Config


logger = logging.getLogger(__name__)


def create_bot(token: str, router: Router, bus: Bus) -> Application:
    """
    Create and configure the Telegram bot application
    with command and callback handlers.

    Args:
        token: The bot token for authentication.
        router: The router holding routes and handlers.
        bus: The bus holding signal handlers.

    Returns:
        A configured Application instance representing the bot.
    """
    application = Application.builder().token(token).build()
    attach_router(router, application)
    attach_bus(bus, application)
    return application


def main():
    app = create_app()

    token = Config.TELEGRAM["bot_token"]
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set in the env variables.")
        return

    bot = create_bot(token, router, bus)
    logger.info("Telegram bot initialized.")

    # Add the run function from bot.py to the file where you set up the bot
    logger.info("Running bot setup.")

    webhook_url = Config.TELEGRAM.get("webhook_url")
    if webhook_url:
        # For production, you should set up a webhook.
        logger.info("Starting a webhook.")
        secret_token = Config.TELEGRAM.get("webhook_secret_token")
        with app.app_context():
            bot.run_webhook(
                listen="127.0.0.1",
                port=8000,
                url_path="telegram",
                secret_token=secret_token,
                webhook_url=webhook_url,
                allowed_updates=Update.ALL_TYPES,
            )
    else:
        # For testing, you can use polling
        logger.info("Starting polling.")
        with app.app_context():
            bot.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
