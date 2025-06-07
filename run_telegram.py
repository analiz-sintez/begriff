import os
import logging
from telegram import Update
from app.telegram.bot import create_bot
from app import create_app
from app.config import Config
from datetime import datetime


def main():
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
        level=logging.INFO,
        format=log_format,
        handlers=[console_handler, file_handler],
    )

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
