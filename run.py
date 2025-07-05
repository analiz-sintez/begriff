import os
import logging
from datetime import datetime
import asyncio
from flask import request, jsonify
from app import create_app
from app.config import Config
from app.telegram.bot import create_bot
from telegram import Update

app = create_app(Config)

# Create the bot application instance
bot_app = create_bot(Config.TELEGRAM["bot_token"])

# Define the webhook URL. This must be a public HTTPS URL.
# Add this to your config.
# e.g., Config.TELEGRAM["webhook_url"] = "https://your.domain.com/telegram"
WEBHOOK_URL = Config.TELEGRAM.get("webhook_url")


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


async def setup_bot():
    """Initializes the bot and sets the webhook."""
    await bot_app.initialize()
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=Config.TELEGRAM.get("webhook_secret_token", None),
        )
        app.logger.info(f"Webhook set to {WEBHOOK_URL}")
    else:
        app.logger.warning("WEBHOOK_URL not set. Webhook not configured.")
    await bot_app.start()


@app.route("/telegram", methods=["POST"])
async def telegram_webhook():
    """Endpoint to receive updates from Telegram."""
    if not bot_app.running:
        return "Bot not running", 503

    try:
        update_data = request.get_json(force=True)
        update = Update.de_json(data=update_data, bot=bot_app.bot)
        await bot_app.process_update(update)
        return "OK", 200
    except Exception as e:
        app.logger.error(f"Error processing update: {e}", exc_info=True)
        return "Error", 500


@app.route("/")
def index():
    """A simple endpoint to check if the server is running."""
    return "Bot server is running."


if __name__ == "__main__":
    setup_logging()
    # The application context is required for logging and other Flask features.
    with app.app_context():
        # Setup the bot asynchronously.
        asyncio.run(setup_bot())

    # Run the Flask web server.
    # For production, use a proper WSGI server like Gunicorn or uWSGI.
    app.run(debug=True, host="0.0.0.0", port=8000)
