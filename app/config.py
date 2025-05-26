import os
from dotenv import load_dotenv


load_dotenv()
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class Config:
    # List of allowed Telegram users
    ALLOWED_USERS = [
        # Add Telegram logins here
        "user1",
        "user2",
        "user3",
    ]

    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL"
    ) or "sqlite:///" + os.path.join(basedir, "data/database.sqlite")

    # Swagger configuration
    SWAGGER = {"title": "Begriff Bot API", "uiversion": 3, "openapi": "3.0.0"}

    LLM = {
        # this one doesn't work because `responses` endpoint is not supported,
        # only `chat` is.
        # "host": "http://192.168.10.22:11434/v1",
        # "model": "qwen3:8b",
        "host": "https://api.openai.com/v1",
        "api_key": os.getenv("OPENAI_API_KEY") or "dummy",
        "model": "gpt-4o-mini",
    }

    TELEGRAM = {"bot_token": os.getenv("TELEGRAM_BOT_TOKEN")}

    FSRS = {"target_retention": 0.9}
