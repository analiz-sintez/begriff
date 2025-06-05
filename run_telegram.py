import os
import logging
from telegram import Update
from app.telegram.bot import create_bot

from app import create_app
from app.config import Config


def main():
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    token = Config.TELEGRAM["bot_token"]
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set in the env variables.")
        return

    bot = create_bot(token)
    logger.info("Telegram bot initialized.")

    # Add the run function from bot.py to the file where you set up the bot
    logger.info("Running bot setup.")

    # For testing, you can use polling
    logger.info("Starting polling.")
    app = create_app(Config)
    with app.app_context():
        bot.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
