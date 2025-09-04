#!/usr/bin/env python3
"""
Locust stress testing configuration for Begriff Telegram bot.
Tests user scenarios through webhook simulation.
"""

import json
import random
import time
from typing import Dict, Any

from locust import HttpUser, task, between
from telegram_utils import (
    TelegramUpdateGenerator, 
    UserSessionManager,
    get_random_sample,
    create_realistic_user_id,
    SAMPLE_URLS,
    SAMPLE_WORDS,
    SAMPLE_EXPLANATIONS,
    CALLBACK_DATA_PATTERNS
)


class TelegramBotUser(HttpUser):
    """Base class for Telegram bot users."""
    
    # Wait between tasks: uniform random 0-1 seconds as specified
    wait_time = between(0, 1)
    
    def on_start(self):
        """Initialize user session."""
        self.user_id = create_realistic_user_id()
        self.username = f"testuser{self.user_id}"
        self.update_generator = TelegramUpdateGenerator()
        self.session_manager = UserSessionManager()
        
        # Start with /start command
        self._send_command("start")
    
    def _send_telegram_update(self, update_data: Dict[str, Any]) -> Any:
        """Send a Telegram update to the bot webhook."""
        response = self.client.post(
            "/telegram",  # Webhook endpoint
            json=update_data,
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": "test_secret"  # If needed
            },
            name="telegram_webhook"
        )
        return response
    
    def _send_command(self, command: str, args: str = "") -> Any:
        """Send a command to the bot."""
        update = self.update_generator.create_command_update(
            self.user_id, command, args, username=self.username
        )
        return self._send_telegram_update(update)
    
    def _send_message(self, text: str) -> Any:
        """Send a text message to the bot."""
        update = self.update_generator.create_message_update(
            self.user_id, text, username=self.username
        )
        return self._send_telegram_update(update)
    
    def _send_callback_query(self, callback_data: str, message_id: int = None) -> Any:
        """Send a callback query (button press) to the bot."""
        update = self.update_generator.create_callback_query_update(
            self.user_id, callback_data, message_id, username=self.username
        )
        return self._send_telegram_update(update)
    
    def _send_url_message(self, url: str) -> Any:
        """Send a message containing a URL."""
        update = self.update_generator.create_url_message_update(
            self.user_id, url, username=self.username
        )
        return self._send_telegram_update(update)


class StudySessionUser(TelegramBotUser):
    """User focused on study sessions."""
    
    weight = 3  # Higher weight for study sessions
    
    @task(5)
    def study_session_flow(self):
        """Complete study session flow."""
        session = self.session_manager.get_session(self.user_id)
        
        if not session.get("study_session_active"):
            # Start study session
            self._send_command("study")
            self.session_manager.update_session(self.user_id, {"study_session_active": True})
            time.sleep(random.uniform(0.5, 1.5))  # Wait for response
        
        # Simulate reviewing cards
        for _ in range(random.randint(1, 5)):
            # Grade the current card
            grade = get_random_sample(CALLBACK_DATA_PATTERNS["study_grade"])
            self._send_callback_query(grade)
            time.sleep(random.uniform(0.5, 2.0))  # Think time
            
            # Possibly continue or stop
            if random.random() < 0.8:  # 80% chance to continue
                continue
            else:
                self._send_callback_query("study_stop")
                self.session_manager.update_session(self.user_id, {"study_session_active": False})
                break
    
    @task(1)
    def check_notes(self):
        """Check notes list."""
        self._send_command("list")
        time.sleep(random.uniform(0.3, 1.0))


class NoteTakingUser(TelegramBotUser):
    """User focused on note taking and explanations."""
    
    weight = 2
    
    @task(3)
    def ask_for_explanation(self):
        """Ask for word explanations."""
        explanation_request = get_random_sample(SAMPLE_EXPLANATIONS)
        self._send_message(explanation_request)
        time.sleep(random.uniform(0.5, 2.0))  # Wait for response
    
    @task(2)
    def ask_for_translation(self):
        """Ask for translation using ?? prefix."""
        word = get_random_sample(SAMPLE_WORDS)
        self._send_message(f"??{word}")
        time.sleep(random.uniform(0.5, 1.5))
    
    @task(1)
    def request_url_recap(self):
        """Send URL for recap."""
        url = get_random_sample(SAMPLE_URLS)
        self._send_url_message(url)
        time.sleep(random.uniform(1.0, 3.0))  # Recaps take longer
    
    @task(1)
    def grammar_check(self):
        """Use grammar check feature."""
        sentence = "This are sentence for check grammar please."
        self._send_message(f"!!{sentence}")
        time.sleep(random.uniform(0.5, 1.5))


class CasualUser(TelegramBotUser):
    """Casual user with mixed behavior."""
    
    weight = 1
    
    @task(2)
    def random_word_lookup(self):
        """Look up random words."""
        word = get_random_sample(SAMPLE_WORDS)
        self._send_message(word)
        time.sleep(random.uniform(0.3, 1.0))
    
    @task(1)
    def help_command(self):
        """Check help."""
        self._send_command("help")
        time.sleep(random.uniform(0.2, 0.8))
    
    @task(1)
    def language_management(self):
        """Change language settings."""
        self._send_command("language")
        time.sleep(random.uniform(0.5, 1.0))
        
        # Sometimes select a language
        if random.random() < 0.5:
            language = get_random_sample(CALLBACK_DATA_PATTERNS["language_select"])
            self._send_callback_query(language)
            time.sleep(random.uniform(0.3, 0.8))


# Additional configuration
class StressTestConfiguration:
    """Configuration for different stress test scenarios."""
    
    # Scenario 1: Light load
    LIGHT_LOAD = {
        "users": 10,
        "spawn_rate": 2,
        "run_time": "30s"
    }
    
    # Scenario 2: Medium load
    MEDIUM_LOAD = {
        "users": 20,
        "spawn_rate": 4,
        "run_time": "30s"
    }
    
    # Scenario 3: Heavy load
    HEAVY_LOAD = {
        "users": 40,
        "spawn_rate": 8,
        "run_time": "30s"
    }
    
    # Scenario 4: Peak load
    PEAK_LOAD = {
        "users": 80,
        "spawn_rate": 16,
        "run_time": "30s"
    }
    
    # Scenario 5: Extreme load
    EXTREME_LOAD = {
        "users": 160,
        "spawn_rate": 32,
        "run_time": "30s"
    }