#!/usr/bin/env python3
"""
Utilities for generating Telegram Update objects for stress testing.
Creates valid JSON payloads that mimic real Telegram webhook updates.
"""

import json
import random
import time
from typing import Dict, Any, Optional, List


class TelegramUpdateGenerator:
    """Generator for various types of Telegram updates."""
    
    def __init__(self):
        self.update_counter = random.randint(100000, 999999)
        self.message_counter = random.randint(10000, 99999)
        
    def _get_next_update_id(self) -> int:
        """Get next sequential update ID."""
        self.update_counter += 1
        return self.update_counter
        
    def _get_next_message_id(self) -> int:
        """Get next sequential message ID."""
        self.message_counter += 1
        return self.message_counter
    
    def _create_user(self, user_id: int, username: str = None) -> Dict[str, Any]:
        """Create a user object."""
        user = {
            "id": user_id,
            "is_bot": False,
            "first_name": f"TestUser{user_id}",
            "language_code": "en"
        }
        if username:
            user["username"] = username
        return user
    
    def _create_chat(self, chat_id: int, chat_type: str = "private") -> Dict[str, Any]:
        """Create a chat object."""
        return {
            "id": chat_id,
            "type": chat_type
        }
    
    def create_message_update(
        self, 
        user_id: int, 
        text: str,
        chat_id: Optional[int] = None,
        username: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a message update."""
        if chat_id is None:
            chat_id = user_id
        
        return {
            "update_id": self._get_next_update_id(),
            "message": {
                "message_id": self._get_next_message_id(),
                "from": self._create_user(user_id, username),
                "chat": self._create_chat(chat_id),
                "date": int(time.time()),
                "text": text
            }
        }
    
    def create_command_update(
        self,
        user_id: int,
        command: str,
        args: str = "",
        chat_id: Optional[int] = None,
        username: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a command update (e.g., /start, /study)."""
        if chat_id is None:
            chat_id = user_id
            
        text = f"/{command}"
        if args:
            text += f" {args}"
        
        update = self.create_message_update(user_id, text, chat_id, username)
        
        # Add entities for command
        update["message"]["entities"] = [
            {
                "offset": 0,
                "length": len(command) + 1,
                "type": "bot_command"
            }
        ]
        
        return update
    
    def create_callback_query_update(
        self,
        user_id: int,
        callback_data: str,
        message_id: Optional[int] = None,
        chat_id: Optional[int] = None,
        username: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a callback query update (button press)."""
        if chat_id is None:
            chat_id = user_id
        if message_id is None:
            message_id = self._get_next_message_id()
        
        return {
            "update_id": self._get_next_update_id(),
            "callback_query": {
                "id": str(random.randint(1000000000, 9999999999)),
                "from": self._create_user(user_id, username),
                "message": {
                    "message_id": message_id,
                    "from": {
                        "id": 123456789,  # Bot ID
                        "is_bot": True,
                        "first_name": "BegriffBot",
                        "username": "begriffbot"
                    },
                    "chat": self._create_chat(chat_id),
                    "date": int(time.time()) - 10,
                    "text": "Mock bot message with buttons"
                },
                "chat_instance": str(random.randint(1000000000, 9999999999)),  # Required field
                "data": callback_data
            }
        }
    
    def create_url_message_update(
        self,
        user_id: int,
        url: str,
        chat_id: Optional[int] = None,
        username: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a message update containing a URL."""
        update = self.create_message_update(user_id, url, chat_id, username)
        
        # Add URL entity
        update["message"]["entities"] = [
            {
                "offset": 0,
                "length": len(url),
                "type": "url"
            }
        ]
        
        return update


class UserSessionManager:
    """Manages user session state for realistic interaction flows."""
    
    def __init__(self):
        self.sessions: Dict[int, Dict[str, Any]] = {}
    
    def get_session(self, user_id: int) -> Dict[str, Any]:
        """Get or create session for user."""
        if user_id not in self.sessions:
            self.sessions[user_id] = {
                "state": "idle",
                "language": "en",
                "native_language": "ru",
                "studied_language": None,
                "current_card_id": None,
                "study_session_active": False,
                "notes_created": 0,
                "cards_studied": 0,
                "last_note_creation": None,
                "message_history": []
            }
        return self.sessions[user_id]
    
    def update_session(self, user_id: int, updates: Dict[str, Any]):
        """Update session data for user."""
        session = self.get_session(user_id)
        session.update(updates)
    
    def mark_note_created(self, user_id: int):
        """Mark that user created a note (should have cards available for study)."""
        session = self.get_session(user_id)
        session["notes_created"] += 1
        session["last_note_creation"] = time.time()
    
    def should_study_now(self, user_id: int) -> bool:
        """Check if user should study based on recent note creation."""
        session = self.get_session(user_id)
        if session["notes_created"] > 0 and session["last_note_creation"]:
            # Study if we created notes recently (within last 5 minutes)
            return (time.time() - session["last_note_creation"]) < 300
        return False
    
    def get_user_language(self, user_id: int) -> str:
        """Get the user's studied language."""
        session = self.get_session(user_id)
        return session.get("studied_language", "german")
    
    def add_message_to_history(self, user_id: int, message_type: str, content: str):
        """Add message to user's history."""
        session = self.get_session(user_id)
        session["message_history"].append({
            "type": message_type,
            "content": content,
            "timestamp": time.time()
        })
        
        # Keep only last 10 messages
        if len(session["message_history"]) > 10:
            session["message_history"] = session["message_history"][-10:]


# Common test data
SAMPLE_URLS = [
    "https://en.wikipedia.org/wiki/Python_(programming_language)",
    "https://docs.python.org/3/tutorial/",
    "https://github.com/python/cpython",
    "https://stackoverflow.com/questions/tagged/python",
    "https://realpython.com/python-basics/"
]

# Wikipedia-focused URLs for heavy network testing (20% of users will use these)
WIKIPEDIA_URLS = [
    "https://en.wikipedia.org/wiki/Machine_learning", 
    "https://en.wikipedia.org/wiki/Artificial_intelligence",
    "https://en.wikipedia.org/wiki/Natural_language_processing",
    "https://en.wikipedia.org/wiki/Deep_learning",
    "https://en.wikipedia.org/wiki/Computer_science",
    "https://en.wikipedia.org/wiki/Software_engineering", 
    "https://en.wikipedia.org/wiki/Data_science",
    "https://en.wikipedia.org/wiki/Programming_language",
    "https://en.wikipedia.org/wiki/Algorithm",
    "https://en.wikipedia.org/wiki/Database",
    "https://en.wikipedia.org/wiki/Web_development",
    "https://en.wikipedia.org/wiki/Cryptography",
    "https://en.wikipedia.org/wiki/Operating_system",
    "https://en.wikipedia.org/wiki/Network_programming",
    "https://en.wikipedia.org/wiki/Cloud_computing"
]

SAMPLE_WORDS = [
    "hello", "world", "python", "programming", "computer",
    "language", "learning", "study", "memory", "vocabulary",
    "explanation", "meaning", "context", "sentence", "grammar",
    "algorithm", "function", "variable", "database", "network",
    "software", "hardware", "internet", "website", "application",
    "development", "testing", "debugging", "framework", "library",
    "interface", "protocol", "security", "encryption", "server",
    "client", "browser", "mobile", "responsive", "optimization"
]

# Words in different languages for users studying those languages
LANGUAGE_SPECIFIC_WORDS = {
    "german": [
        "Hallo", "Welt", "Computer", "Programmierung", "Sprache",
        "Lernen", "Studium", "Gedächtnis", "Wortschatz", "Erklärung",
        "Bedeutung", "Kontext", "Satz", "Grammatik", "Algorithmus",
        "Funktion", "Variable", "Datenbank", "Netzwerk", "Software",
        "Hardware", "Internet", "Website", "Anwendung", "Entwicklung"
    ],
    "french": [
        "Bonjour", "Monde", "Ordinateur", "Programmation", "Langue",
        "Apprentissage", "Étude", "Mémoire", "Vocabulaire", "Explication", 
        "Signification", "Contexte", "Phrase", "Grammaire", "Algorithme",
        "Fonction", "Variable", "Base de données", "Réseau", "Logiciel",
        "Matériel", "Internet", "Site web", "Application", "Développement"
    ],
    "spanish": [
        "Hola", "Mundo", "Computadora", "Programación", "Idioma",
        "Aprendizaje", "Estudio", "Memoria", "Vocabulario", "Explicación",
        "Significado", "Contexto", "Oración", "Gramática", "Algoritmo", 
        "Función", "Variable", "Base de datos", "Red", "Software",
        "Hardware", "Internet", "Sitio web", "Aplicación", "Desarrollo"
    ],
    "russian": [
        "Привет", "Мир", "Компьютер", "Программирование", "Язык",
        "Обучение", "Изучение", "Память", "Словарь", "Объяснение",
        "Значение", "Контекст", "Предложение", "Грамматика", "Алгоритм",
        "Функция", "Переменная", "База данных", "Сеть", "Программное обеспечение",
        "Оборудование", "Интернет", "Веб-сайт", "Приложение", "Разработка"
    ],
    "italian": [
        "Ciao", "Mondo", "Computer", "Programmazione", "Lingua", 
        "Apprendimento", "Studio", "Memoria", "Vocabolario", "Spiegazione",
        "Significato", "Contesto", "Frase", "Grammatica", "Algoritmo",
        "Funzione", "Variabile", "Database", "Rete", "Software",
        "Hardware", "Internet", "Sito web", "Applicazione", "Sviluppo"
    ]
}

SAMPLE_EXPLANATIONS = [
    "What does 'serendipity' mean?",
    "Explain the word 'ubiquitous'",
    "What is the meaning of 'ephemeral'?",
    "Can you explain 'paradigm'?",
    "What does 'dichotomy' mean?",
    "Define 'algorithm'",
    "What is 'encryption'?",
    "Explain 'optimization'",
    "What does 'responsive' mean?",
    "Define 'protocol'",
    "What is a 'framework'?",
    "Explain 'debugging'",
    "What does 'scalable' mean?",
    "Define 'implementation'",
    "What is 'authentication'?"
]

CALLBACK_DATA_PATTERNS = {
    "study_grade": ["study_grade:again", "study_grade:hard", "study_grade:good", "study_grade:easy"],
    "study_answer": ["study_answer"],
    "study_next": ["study_next"],
    "study_stop": ["study_stop"],
    "language_select": ["language_select:en", "language_select:de", "language_select:fr", "language_select:es", "language_select:ru", "language_select:it", "language_select:pt"],
}


def get_random_sample(sample_list: List[str]) -> str:
    """Get random item from a sample list."""
    return random.choice(sample_list)


def get_words_for_language(language: str) -> List[str]:
    """Get appropriate word list for a given study language."""
    if language in LANGUAGE_SPECIFIC_WORDS:
        return LANGUAGE_SPECIFIC_WORDS[language]
    else:
        return SAMPLE_WORDS  # Fallback to English words


def create_realistic_user_id() -> int:
    """Create a realistic-looking Telegram user ID."""
    return random.randint(100000000, 999999999)