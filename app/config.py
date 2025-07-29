import os
from dotenv import load_dotenv


load_dotenv()
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class Config:
    AUTHENTICATION = {
        # If `allowed_logins` is not empty, use it as a whitelist:
        # allow only users from it.
        "allowed_logins": [],
        # If `blocked_users` is not empty, use it as a blacklist:
        # forbid users from it.
        "blocked_logins": [],
        # Admins can see overall statistics and control access.
        "admin_logins": [],
    }

    SIGNALS = {
        # Where to store the log of signals emitted:.
        # log — just dump them to the app log (see `./logs`)
        # db — save them to the app database into `emitted_events` table
        "logging_backend": "db",
    }

    LANGUAGE = {
        "defaults": {"study": "en", "native": "ru"},
        "study_languages": [
            # ... languages ordered by speakers count:
            "en",  # 1.7b — English
            # "zh",  # 1.3b — (Simplifed) Chinese
            # "hi",  # 0.6b — Hindi
            "es",  # 0.5b — Spanish
            # "ar",  # 0.4b — Arabic (Egyptian kind)
            # "ur",  # 0.3b — Urdu (Pakistan)
            "fr",  # 0.3b — French
            # "bn",  # 0.3b — Bangla (Bangladesh)
            "pt",  # 250m — Portuguese (Portugal kind, but there's Brazil etc)
            "ru",  # 200m — Russian
            "de",  # 150m — German
            # "ja",  # 130m — Japanese
            # ... here go various dialects from Indna, for now we'll skip them.
            # ... those are tens of mlns each:
            # "fa",
            # "vi",
            "tr",
            # "ko",
            # "fil",
            "it",
            # "th",
            "pl",
            # ... from here the list goes opinionated.
            "uk",
            "sr",
            "hy",
            # "ka",
        ],
        # this is completely cosmetic, just to draw flags properly
        "territories": {
            "en": "GB",
            "zh": "CN",
            "hi": "IN",
            "es": "ES",
            "ar": "EG",
            "ur": "PK",
            "fr": "FR",
            "bn": "BD",
            "pt": "PT",
            "ru": "RU",
            "de": "DE",
            "ja": "JP",
            "fa": "IR",
            "vi": "VN",
            "tr": "TR",
            "ko": "KR",
            "fil": "PH",
            "it": "IT",
            "th": "TH",
            "pl": "PL",
            "uk": "UA",
            "sr": "RS",
            "hy": "AM",
            "ka": "GE",
        },
    }

    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL"
    ) or "sqlite:///" + os.path.join(basedir, "data/database.sqlite")

    # Swagger configuration
    SWAGGER = {"title": "Begriff Bot API", "uiversion": 3, "openapi": "3.0.0"}

    LLM = {
        # # Ollama config
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
            "recap": "gpt-4o",
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
        "enable": True,
        "model": "imagen-4.0-generate-preview-06-06",
        "prompt": "%s (sketchy, colorful)",
        "vertexai_project_id": "begriff",
    }

    TELEGRAM = {
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "webhook_url": os.getenv("TELEGRAM_WEBHOOK_URL"),
        "webhook_secret_token": os.getenv("TELEGRAM_WEBHOOK_SECRET_TOKEN"),
    }

    FSRS = {
        "target_retention": 0.9,
        "mature_threshold": 2,
        "new_cards_per_session": 10,
        "bury_siblings": True,
        "card_is_leech": {
            "difficulty": 8.5,
            "view_cnt": 5,
        },
    }
