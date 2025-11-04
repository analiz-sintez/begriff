import os
from dotenv import load_dotenv


load_dotenv()
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class Config:
    ################################################################
    # Nachricht part

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
            "default": "gpt-5-mini",
        },
    }

    IMAGE = {
        "enable": True,
        "model": "imagen-4.0-generate-preview-06-06",
        "vertexai_project_id": "begriff",
    }

    ################################################################
    # Begriff-specific part

    DEFAULTS = {
        "study_language": "en",
        "native_language": "en",
    }

    LANGUAGES = {
        "_defaults": {
            "features": {
                "recap": True,
                "base_form": True,
                "image_generation": True,
                "inject_notes": [
                    "recap",
                    # "explanation",
                    "example",
                ],
            },
            "models": {
                "default": "gpt-4.1-mini",
                "base_form": "gpt-4.1-mini",
                "explanation": "gpt-4.1-mini",
                "recap": "gpt-5",
                "clarification": "gpt-5-mini",
                "examples": "gpt-4.1-mini",
            },
            "prompts": {
                "base_form": """Convert the following {{ language }} word or phrase to its base form (e.g., infinitive for verbs, singular for nouns).

Instructions:
- Return only the word in its base form: no markup, comments or explanations.
- If the word is already in its base form, return it as is.

Examples:
- English: trees — tree, cogitated — to cogitate
- German, Häuse — das Haus, Bäume — der Baum, Loch — das Loch""",
                "explanation": """You are an expert linguist tasked with explaining words in simple terms. Your task is to explain the given {{ src_language }} word or phrase in {{ dst_language }} using the following guidelines:

- If a word has multiple significant meanings, provide explanations for the two most common contexts. Indicate any special contextual use (e.g., official documents, office slang, street slang) in square brackets. Don't put empty lines between meanings. Use '.' in the end of each meaning.
- Do not use the explained word in your explanation. 
- The explanation should be entirely in {{ dst_language }}.

Example 1 (for English).
Prompt: to gorge
Reply: To eat a large amount quickly.

Example 2 (for English).
Prompt: fixer
Reply: [General] Someone who solves problems, often in a quick or discreet manner. [Informal/Slang] A person who helps others by arranging things behind the scenes. """,
                "recap": """You are {{ language }} tutor helping a student to learn new language. The student studies new words using flashcards, so it would be beneficial for them to see the words in use in real text.

Please summarize the following text into one paragraph using simple {{ language }}.

Instructions:
- Create one concise paragraph of 100-150 words.
- Use simple language, and write only in {{ language }}.
- Keep the summary simple and clear.""",
                "image": "%s (sketchy, colorful)",
                "clarification": """You are {{ language }} tutor helping a student to learn new language. Their native language is {{ native_language }}.

You will be given a word or phrase which is tricky for the student. There could be form or word, conjugation, articles or other complexity. Your task is to unravel that and clarify what is happening and how it works. Give a short and clear comment.

Your answer should be in {{ native_language }}.

Keep the tone terse and structural. Don't say "Great question!" or add "Feel free to ask ..." since it does not add to the answer.""",
                "mistakes": """You are a language tutor. A student has written the following text in {{ src_language }}.
Please identify up to 3 main grammatical or lexical mistakes in their text.
For each mistake:
1. Briefly explain the mistake in {{ dst_language }}.
2. Provide the corrected version of the problematic part of the sentence in {{ src_language }}.

Present your findings as a numbered list.
If there are no mistakes, or if the text is too short to analyze, simply state that in {{ dst_language }}.

Example for a student writing in English (and explanations in English):
Student's text: "I will can go to the cinema tomorrow."
Your response:
1. Incorrect modal verb usage: You cannot use "will" and "can" together.
   Corrected: "I will be able to go to the cinema tomorrow." or "I can go to the cinema tomorrow."

Student's text: "He go to school every day."
Your response:
1. Subject-verb agreement error: The verb "go" should be "goes" for the third-person singular pronoun "He".
   Corrected: "He goes to school every day."
""",
                "examples": """You are {{ language }} tutor helping a student to learn new language.

Generate one usage example for the given word or phrase.

- Example should be a full sentence. Use the word in the sentence in the appropriate form.
- Enclose the word with double braces.
- If a word has multiple different meanings, provide an example showing the most common meaning. Indicate this meaning in square brackets in {{ language }} at the line start with one or two words.

{% if not examples %}
The pattern:

1. The student studies German, the word is: "Konto".

Your response:

[Bankwesen] Ich habe ein neues {{ '{{Konto}}' }} bei der Bank eröffnet, um mein Geld sicher zu verwalten.

2. The student studies English, the word is: "bare".

Your response:

[naked] The tree stood {{ '{{bare}}' }} against the gray winter sky, without any leaves.
{% else %}
Here are the examples you've already generated for this word. Copy the format, but create a new, distinct example, showing another meaning of the word or using another style or form, e.g. a question or an exclamation instead of a statement.
{% for example in examples %}{{ example }}{% endfor %}
{% endif %}

The word is:
""",
            },
            "card_templates": {
                "direct_front": "{field1}",
                "direct_back": "{field1}\n\n{display_text}",
                "reverse_front": "{display_text}",
                "reverse_back": "{display_text}\n\n{field1}",
            },
        },
        # 1.7b — English
        "en": {
            "territory": "GB",
            "prompts": {
                "base_form": """Convert the following English word to its base form.

- Return only the word in its base form: no markup, comments or explanations.
- If the word is already in its base form, return it as is.
- For verbs, always use 'to'.

Examples:
trees — tree
cogitated — to cogitate""",
            },
        },
        # 1.3b — (Simplifed) Chinese
        # "zh": {'territory': 'CN'},
        # 0.6b — Hindi
        # "hi": {'territory': 'IN'},
        # 0.5b — Spanish
        "es": {
            "territory": "ES",
        },
        # 0.4b — Arabic (Egyptian kind)
        # "ar": {'territory': 'EG'},
        # 0.3b — Urdu (Pakistan)
        # "ur": {'territory': 'PK'},
        # 0.3b — French
        "fr": {
            "territory": "FR",
        },
        # 0.3b — Bangla (Bangladesh)
        # "bn": {'territory': 'BD'},
        # 250m — Portuguese (Portugal kind, but there's Brazil etc)
        "pt": {
            "territory": "PT",
        },
        # 200m — Russian
        "ru": {
            "territory": "RU",
        },
        # 150m — German
        "de": {
            "territory": "DE",
            "prompts": {
                "base_form": """Convert the following German word to its base form.

- Return only the word in its base form: no markup, comments or explanations.
- If the word is already in its base form, return it as is.
- For nouns, always include the article.

Examples:
Häuse — das Haus
Bäume — der Baum""",
            },
        },
        # 130m — Japanese
        # "ja": {'territory': 'JP'},
        # ... here go various dialects from Indna, for now we'll skip them.
        # ... those are tens of mlns each:
        # Farsi (Iran)
        # "fa": {'territory': 'IR'},
        # Vietnamese
        # "vi": {'territory': 'VN'},
        # Turkish
        "tr": {
            "territory": "TR",
        },
        # Korean
        # "ko": {'territory': 'KR'},
        # Philippinese
        # "fil": {'territory': 'PH'},
        # Italian
        "it": {
            "territory": "IT",
        },
        # Thai
        # "th": {'territory': 'TH'},
        # Polish
        "pl": {
            "territory": "PL",
        },
        # ... from here the list goes opinionated.
        # Ukrainian
        "uk": {
            "territory": "UA",
        },
        # Serbian
        "sr": {
            "territory": "RS",
        },
        # Armenian
        "hy": {
            "territory": "AM",
            "features": {
                "recap": False,
                "base_form": False,
            },
        },
        # Georgian
        # "ka": {'territory': 'GE'},
    }

    TELEGRAM = {
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "webhook_url": os.getenv("TELEGRAM_WEBHOOK_URL"),
        "webhook_secret_token": os.getenv("TELEGRAM_WEBHOOK_SECRET_TOKEN"),
    }

    TEMPLATES = {
        "sharable_post": """*{{ word | trim}}* —
{{ explanation | trim }}

{% for example in examples %}
🔸{% if example.field2 %}_{{example.field2}}_ {% endif %}{{ example.field1 | trim | replace('{{','||') | replace('}}', '||') }}
{% endfor %}

@BegriffBot 😻
"""
    }

    UX = {
        # Try to guess if a user asks a translation *from* their native language
        # or a translation *to* it (the regular flow).
        # This is far from perfect so it's disabled by default.
        "guess_input_language": True,
        "guess_input_language_threshold": 0.8,
        "simple_card_grades": True,
        "wait_second_lookup": True,
    }

    FSRS = {
        "target_retention": 0.9,
        # Stability above which the card is considered mature:
        # (Stability is number of days after which the estimated chance
        # to recall a card drops from 100% to 90%.)
        "mature_threshold": 7,
        "new_cards_per_session": 10,
        "bury_siblings": True,
        "card_is_leech": {
            "difficulty": 8.5,
            "view_cnt": 5,
        },
        "inject_maturity": ["young"],
        "inject_count": 10,
    }
