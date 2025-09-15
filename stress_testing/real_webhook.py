#!/usr/bin/env python3
"""
Real webhook server that processes actual bot logic with mock services.
Integrates with nachricht framework and real database operations.
Only mocks external dependencies - uses real application logic.
"""

import sys
import os
import json
import time
import logging
from pathlib import Path
from flask import Flask, request, jsonify

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import StressTestConfig, MockServiceConfig

# Apply test environment before importing the app
StressTestConfig.apply_test_environment()

# CRITICAL: Mock ALL external dependencies BEFORE any imports
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock

# Mock Google Auth to avoid authentication issues
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/dev/null"  # Dummy path

# 1. Mock Vertex AI modules before they're imported
mock_vertexai = MagicMock()
mock_vision_models = MagicMock()

class MockImageGenerationModel:
    @classmethod
    def from_pretrained(cls, model_name):
        logger = logging.getLogger(__name__)
        logger.debug(f"Mock ImageGenerationModel.from_pretrained called with {model_name}")
        mock = MagicMock()
        mock.generate_images.return_value.images = []
        return mock

mock_vision_models.ImageGenerationModel = MockImageGenerationModel
sys.modules['vertexai'] = mock_vertexai
sys.modules['vertexai.preview'] = MagicMock()
sys.modules['vertexai.preview.vision_models'] = mock_vision_models

# 2. Mock lingua library for language detection
class MockLanguage:
    def __init__(self, name="ENGLISH"):
        self.name = name
    
    @staticmethod
    def from_str(lang_str):
        # Map common language strings to proper names
        lang_map = {
            "en": "ENGLISH", "english": "ENGLISH",
            "ru": "RUSSIAN", "russian": "RUSSIAN", 
            "es": "SPANISH", "spanish": "SPANISH",
            "de": "GERMAN", "german": "GERMAN",
            "fr": "FRENCH", "french": "FRENCH"
        }
        mapped_name = lang_map.get(lang_str.lower(), lang_str.upper())
        return MockLanguage(name=mapped_name)
    
    def __str__(self):
        return self.name

class MockConfidenceValue:
    def __init__(self, language="ENGLISH", value=0.95):
        # language should be a MockLanguage object, not a string
        if isinstance(language, str):
            self.language = MockLanguage(name=language)
        else:
            self.language = language
        self.value = value

class MockLanguageDetectorBuilder:
    @staticmethod
    def from_all_languages():
        return MockLanguageDetectorBuilder()
    
    @staticmethod
    def from_languages(*languages):
        return MockLanguageDetectorBuilder()
    
    def build(self):
        mock_detector = MagicMock()
        # Return properly structured confidence values
        mock_detector.compute_language_confidence_values.return_value = [
            MockConfidenceValue(MockLanguage("ENGLISH"), 0.95),
            MockConfidenceValue(MockLanguage("RUSSIAN"), 0.03),
            MockConfidenceValue(MockLanguage("SPANISH"), 0.02)
        ]
        return mock_detector

mock_lingua = MagicMock()
mock_lingua.Language = MockLanguage
mock_lingua.LanguageDetectorBuilder = MockLanguageDetectorBuilder
mock_lingua.ConfidenceValue = MockConfidenceValue
sys.modules['lingua'] = mock_lingua

# 3. Mock requests selectively - allow Wikipedia but block other external APIs
import requests
original_post = requests.post
original_get = requests.get

def selective_mock_post(url, *args, **kwargs):
    logger = logging.getLogger(__name__)
    if ("localhost" in url or 
        "wikipedia.org" in url or 
        "wikimedia.org" in url):
        # Allow calls to local services AND Wikipedia (for realistic load testing)
        return original_post(url, *args, **kwargs)
    else:
        logger.debug(f"Mocking external POST request to: {url}")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "mocked_external_call"}
        return mock_response

def selective_mock_get(url, *args, **kwargs):
    logger = logging.getLogger(__name__)
    if ("localhost" in url or 
        "wikipedia.org" in url or 
        "wikimedia.org" in url):
        # Allow calls to local services AND Wikipedia (for realistic load testing)
        return original_get(url, *args, **kwargs)
    else:
        logger.debug(f"Mocking external GET request to: {url}")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Mock webpage content for stress testing"
        return mock_response

requests.post = selective_mock_post
requests.get = selective_mock_get

# 4. CRITICAL: Mock OpenAI client to redirect to our mock service
class MockOpenAIClient:
    def __init__(self, api_key=None, base_url=None, **kwargs):
        self.api_key = api_key
        # Force all OpenAI calls to our mock service regardless of config
        self.base_url = "http://localhost:8001/v1"
        self.chat = MockChatCompletions()
        logger = logging.getLogger(__name__)
        logger.info(f"MockOpenAIClient created with base_url: {self.base_url}")

class MockChatCompletions:
    def __init__(self):
        self.completions = MockCompletions()

class MockOpenAIResponse:
    """Mock response object that mimics OpenAI's response structure."""
    def __init__(self, response_dict):
        self.choices = [MockChoice(choice) for choice in response_dict.get("choices", [])]
        self.usage = response_dict.get("usage", {})
        self.id = response_dict.get("id", "mock_id")
        self.model = response_dict.get("model", "mock_model")

class MockChoice:
    def __init__(self, choice_dict):
        self.message = MockMessage(choice_dict.get("message", {}))
        self.finish_reason = choice_dict.get("finish_reason", "stop")
        self.index = choice_dict.get("index", 0)

class MockMessage:
    def __init__(self, message_dict):
        self.content = message_dict.get("content", "Mock response")
        self.role = message_dict.get("role", "assistant")

class MockCompletions:
    def create(self, **kwargs):
        logger = logging.getLogger(__name__)
        logger.debug(f"Redirecting OpenAI call to mock service with model: {kwargs.get('model', 'unknown')}")
        
        # Make actual HTTP call to our mock LLM service
        import requests
        try:
            response = requests.post(
                "http://localhost:8001/v1/chat/completions",
                json=kwargs,
                timeout=10
            )
            response_dict = response.json()
            # Wrap in OpenAI-compatible object
            return MockOpenAIResponse(response_dict)
        except Exception as e:
            logger.error(f"Mock LLM service call failed: {e}")
            # Return a fallback response wrapped in proper object
            fallback_dict = {
                "choices": [
                    {
                        "message": {
                            "content": "Mock LLM response (service unavailable)"
                        }
                    }
                ]
            }
            return MockOpenAIResponse(fallback_dict)

# Mock the OpenAI module before any imports
mock_openai = MagicMock()
mock_openai.OpenAI = MockOpenAIClient
mock_openai.AsyncOpenAI = MockOpenAIClient  # For async calls
sys.modules['openai'] = mock_openai

# CRITICAL: Override app config BEFORE importing app module
# This must happen before app/__init__.py runs and initializes the LLM client
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import Config first and override it
from app.config import Config
mock_config = MockServiceConfig.get_updated_app_config()
Config.LLM.update(mock_config["LLM"])
Config.IMAGE.update(mock_config["IMAGE"])

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"Pre-import LLM config: {Config.LLM['host']}")

# Check if nachricht respects the config override
import os
logger.info(f"Environment OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY')}")

# NOW import the app modules (LLM client will use our overridden config)
from app import router, bus, create_app
from telegram import Update
from telegram.ext import Application
from nachricht.messenger.telegram import attach_bus, attach_router

# Debug: Check what the LLM client actually got configured with
try:
    from app import llm_client
    logger.info(f"LLM client host: {getattr(llm_client, '_host', 'unknown')}")
    logger.info(f"LLM client api_key: {getattr(llm_client, '_api_key', 'unknown')[:10]}...")
except Exception as e:
    logger.warning(f"Could not inspect LLM client: {e}")

# Global variables
main_app = None
telegram_app = None
request_count = 0
start_time = time.time()

def create_real_webhook_app():
    """Create webhook app that integrates with real bot logic."""
    global main_app, telegram_app
    
    logger.info(f"Using mock LLM at: {Config.LLM['host']}")
    logger.info(f"Mock LLM API key: {Config.LLM['api_key']}")
    logger.info(f"Using mock Image service for project: {Config.IMAGE['vertexai_project_id']}")
    
    # Create the main app to initialize database and services
    main_app = create_app()
    
    # Create Telegram bot application with real handlers
    token = Config.TELEGRAM["bot_token"]
    telegram_app = Application.builder().token(token).build()
    attach_router(router, telegram_app)
    attach_bus(bus, telegram_app)
    
    # The bot will use our local mock Telegram API server
    # Set the bot API URL to point to our mock server
    telegram_app.bot._base_url = f"{StressTestConfig.MOCK_TELEGRAM_API_URL}/bot{Config.TELEGRAM['bot_token']}"
    
    # Now we can safely initialize the bot - it will call our mock API
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(telegram_app.initialize())
        logger.info("Telegram application initialized with mock API server")
    except Exception as e:
        logger.error(f"Failed to initialize bot with mock API: {e}")
        raise
    finally:
        loop.close()
    
    logger.info("Telegram application initialized with mock bot properties for stress testing")
    
    logger.info("Real Telegram bot initialized with mock services")
    
    # Create Flask app for webhook handling
    webhook_app = Flask(__name__)
    
    @webhook_app.route('/telegram', methods=['POST'])
    def handle_webhook():
        """Handle incoming Telegram webhooks with real bot processing."""
        global request_count
        request_count += 1
        
        request_start_time = time.time()
        
        try:
            # Get JSON data
            update_data = request.get_json()
            if not update_data:
                logger.warning("No JSON data in request")
                return jsonify({"ok": False, "error": "No JSON data"}), 400
            
            # Create Telegram Update object
            try:
                update = Update.de_json(update_data, telegram_app.bot)
                if not update:
                    logger.warning("Failed to parse update")
                    return jsonify({"ok": False, "error": "Invalid update format"}), 400
            except Exception as e:
                logger.error(f"Error parsing update: {e}")
                return jsonify({"ok": False, "error": f"Parse error: {str(e)}"}), 400
            
            # Process with real bot logic using the nachricht framework
            with main_app.app_context():
                try:
                    logger.debug(f"Processing update {update.update_id} with real bot logic")
                    
                    # Use the real telegram bot application to process the update
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    try:
                        # Process the update through the real bot handlers
                        loop.run_until_complete(telegram_app.process_update(update))
                        
                        # Log what was processed for debugging
                        update_type = "unknown"
                        if update.message:
                            if update.message.text and update.message.text.startswith('/'):
                                update_type = f"command: {update.message.text.split()[0]}"
                            elif update.message.text:
                                update_type = f"message: {update.message.text[:20]}..."
                        elif update.callback_query:
                            update_type = f"callback: {update.callback_query.data}"
                        
                        logger.debug(f"Processed {update_type} from user {update.effective_user.id if update.effective_user else 'unknown'}")
                        
                    finally:
                        loop.close()
                    
                    processing_time = (time.time() - request_start_time) * 1000
                    logger.info(f"Request #{request_count}: Update {update.update_id} processed in {processing_time:.0f}ms")
                    
                    return jsonify({"ok": True, "processing_time_ms": round(processing_time, 2)})
                    
                except Exception as e:
                    processing_time = (time.time() - request_start_time) * 1000
                    logger.error(f"Error processing update {update.update_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    return jsonify({
                        "ok": False, 
                        "error": f"Processing error: {str(e)}", 
                        "processing_time_ms": round(processing_time, 2)
                    }), 500
                    
        except Exception as e:
            processing_time = (time.time() - request_start_time) * 1000
            logger.error(f"Webhook error: {e}")
            return jsonify({
                "ok": False, 
                "error": f"Webhook error: {str(e)}", 
                "processing_time_ms": round(processing_time, 2)
            }), 500
    
    @webhook_app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint with stats."""
        uptime = time.time() - start_time
        return jsonify({
            "status": "healthy",
            "service": "real-webhook",
            "uptime_seconds": round(uptime, 2),
            "requests_handled": request_count,
            "requests_per_second": round(request_count / uptime if uptime > 0 else 0, 2)
        })
    
    @webhook_app.route('/stats', methods=['GET'])
    def get_stats():
        """Get detailed request statistics."""
        uptime = time.time() - start_time
        return jsonify({
            "requests_total": request_count,
            "uptime_seconds": round(uptime, 2),
            "requests_per_second": round(request_count / uptime if uptime > 0 else 0, 2),
            "start_time": start_time,
            "mock_llm_url": StressTestConfig.MOCK_LLM_URL,
            "mock_image_url": StressTestConfig.MOCK_IMAGE_URL
        })
    
    return webhook_app


# No more simulation functions needed - using real bot logic!


def cleanup_telegram_app():
    """Cleanup the Telegram application."""
    global telegram_app
    if telegram_app:
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(telegram_app.shutdown())
            loop.close()
            logger.info("Telegram application cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up Telegram app: {e}")


def main():
    """Run the real webhook server."""
    
    print("=== Real Begriff Webhook with Mock Services ===")
    print(f"Port: {StressTestConfig.TELEGRAM_BOT_PORT}")
    print(f"Mock LLM: {StressTestConfig.MOCK_LLM_URL}")
    print(f"Mock Image: {StressTestConfig.MOCK_IMAGE_URL}")
    
    # Check database exists
    project_dir = Path(__file__).parent.parent
    db_path = project_dir / "data" / "test_database.sqlite"
    
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1
    
    print(f"✓ Using database: {db_path}")
    
    # Create webhook app
    try:
        webhook_app = create_real_webhook_app()
        
        print("✓ Real webhook server initialized")
        print("✓ Connected to mock LLM and image services")
        print(f"Listening on: 127.0.0.1:{StressTestConfig.TELEGRAM_BOT_PORT}")
        print(f"Webhook endpoint: /telegram")
        print("Ready for real bot logic stress testing!")
        
        # Setup cleanup on exit
        import atexit
        atexit.register(cleanup_telegram_app)
        
        # Run the Flask app
        webhook_app.run(
            host='127.0.0.1',
            port=StressTestConfig.TELEGRAM_BOT_PORT,
            debug=False,
            threaded=True  # Allow concurrent requests
        )
        
    except KeyboardInterrupt:
        print("\nShutting down webhook server...")
        cleanup_telegram_app()
        return 0
    except Exception as e:
        logger.error(f"Error running webhook server: {e}")
        import traceback
        traceback.print_exc()
        cleanup_telegram_app()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())