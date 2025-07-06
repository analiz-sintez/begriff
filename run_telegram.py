import os
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import Application

from core import create_app
from core.bus import Bus
from core.messenger import Router
from core.messenger.telegram import attach_bus, attach_router

from app import bus, router
import app.telegram  # load business logic: routes and signals
from app.config import Config


def setup_logging():
    # Set up logging:
    # ... ensure the directory for logs exists
    log_dir = "./logs"
    os.makedirs(log_dir, exist_ok=True)
    log_filename = (
        f"telegram-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.log"
    )
    # ... set handlers and their levels
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    file_handler = logging.FileHandler(f"{log_dir}/{log_filename}")
    file_handler.setLevel(logging.DEBUG)
    # ... install handlers and set common settings
    log_format = "%(asctime)s\t%(name)s\t%(levelname)s\t%(message)s"
    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        handlers=[console_handler, file_handler],
    )


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
    setup_logging()
    logger = logging.getLogger(__name__)

    token = Config.TELEGRAM["bot_token"]
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set in the env variables.")
        return

    bot = create_bot(token, router, bus)
    logger.info("Telegram bot initialized.")

    # Add the run function from bot.py to the file where you set up the bot
    logger.info("Running bot setup.")

    app = create_app(Config)

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
