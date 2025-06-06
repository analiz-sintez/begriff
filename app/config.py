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
        # # Ollama config
        # # this one doesn't work because `responses` endpoint is not supported,
        # # only `chat` is.
        # "host": "http://localhost:11434/v1",
        # "api_key": "ollama",
        # "models": {
        #     "default": "olmo2:7b",
        #     "base_form": "olmo2:7b",
        #     "explanation": "olmo2:7b",
        #     "recap": "olmo2:7b",
        # },
        # OpenAI config
        "host": "https://api.openai.com/v1",
        "api_key": os.getenv("OPENAI_API_KEY") or "dummy",
        "models": {
            "default": "gpt-4.1-mini",
            "base_form": "gpt-4.1-mini",
            "explanation": "gpt-4.1-mini",
            "recap": "gpt-4o-latest",
        },
        # General settings
        "inject_notes": [
            # "explanation",
            "recap",
        ],
        "inject_maturity": ["young"],
        "inject_count": 10,
        "convert_to_base_form": True,
    }

    IMAGE = {
        "model": "imagen-4.0-generate-preview-05-20",
        "prompt": "%s (sketchy, colorful)",
        "vertexai_project_id": "begriff",
    }

    TELEGRAM = {"bot_token": os.getenv("TELEGRAM_BOT_TOKEN")}

    FSRS = {
        "target_retention": 0.9,
        "mature_threshold": 2,
        "new_cards_per_session": 10,
        "bury_siblings": True,
        "card_is_leech": {
            "difficulty": 5.0,
            "view_cnt": 1,
        },
    }
