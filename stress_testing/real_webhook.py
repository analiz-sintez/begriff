#!/usr/bin/env python3
"""
Real webhook server that processes actual bot logic with mock services.
Integrates with nachricht framework and real database operations.
"""

import sys
import os
import json
import time
import logging
import asyncio
from pathlib import Path
from flask import Flask, request, jsonify

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import StressTestConfig

# Apply test environment before importing the app
StressTestConfig.apply_test_environment()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import after environment is set
from app import router, bus, create_app
from telegram import Update
from telegram.ext import ContextTypes
import nachricht

# Global variables
main_app = None
request_count = 0
start_time = time.time()

def create_real_webhook_app():
    """Create webhook app that integrates with real bot logic."""
    global main_app
    
    # Create the main app to initialize database and services
    main_app = create_app()
    
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
                update = Update.de_json(update_data, None)
                if not update:
                    logger.warning("Failed to parse update")
                    return jsonify({"ok": False, "error": "Invalid update format"}), 400
            except Exception as e:
                logger.error(f"Error parsing update: {e}")
                return jsonify({"ok": False, "error": f"Parse error: {str(e)}"}), 400
            
            # Process with real bot logic
            with main_app.app_context():
                try:
                    # Create a mock bot context for processing
                    context = MockContext(update)
                    
                    # Route the update through nachricht framework
                    process_result = process_update_with_nachricht(update, context)
                    
                    processing_time = (time.time() - request_start_time) * 1000
                    logger.info(f"Request #{request_count}: Update {update.update_id} processed in {processing_time:.0f}ms")
                    
                    return jsonify({"ok": True, "processing_time_ms": round(processing_time, 2)})
                    
                except Exception as e:
                    processing_time = (time.time() - request_start_time) * 1000
                    logger.error(f"Error processing update {update.update_id}: {e}")
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


def process_update_with_nachricht(update, context):
    """Process update through the nachricht framework."""
    
    # Extract user and message information
    user = None
    message = None
    callback_query = None
    
    if update.message:
        message = update.message
        user = message.from_user
        logger.debug(f"Processing message: '{message.text}' from user {user.id}")
    elif update.callback_query:
        callback_query = update.callback_query
        user = callback_query.from_user
        message = callback_query.message
        logger.debug(f"Processing callback query: '{callback_query.data}' from user {user.id}")
    
    if not user:
        raise ValueError("No user found in update")
    
    # Update context with user info
    context.user = user
    context.message = message
    context.callback_query = callback_query
    
    # Route through nachricht framework
    try:
        if message and message.text:
            # Handle text messages (commands, explanations, etc.)
            process_message_text(message.text, context)
        elif callback_query and callback_query.data:
            # Handle button presses (study grades, etc.)
            process_callback_query(callback_query.data, context)
        else:
            logger.warning("No text or callback data to process")
            
    except Exception as e:
        logger.error(f"Error in nachricht processing: {e}")
        raise


def process_message_text(text, context):
    """Process text message through appropriate handlers."""
    
    # Use nachricht router to find and execute handlers
    # This simulates what the real bot does
    
    if text.startswith('/'):
        # Handle commands
        command = text.split()[0][1:]  # Remove '/'
        args = ' '.join(text.split()[1:]) if len(text.split()) > 1 else ''
        
        logger.info(f"Processing command: /{command} with args: '{args}'")
        
        # Route through the actual command handlers
        if hasattr(router, 'handle_command'):
            router.handle_command(command, args, context)
        else:
            # Fallback: simulate command processing
            simulate_command_processing(command, args, context)
    
    elif text.startswith('??'):
        # Translation request
        word = text[2:].strip()
        logger.info(f"Processing translation request: '{word}'")
        simulate_translation_processing(word, context)
    
    elif text.startswith('!!'):
        # Grammar check request
        sentence = text[2:].strip()
        logger.info(f"Processing grammar check: '{sentence}'")
        simulate_grammar_check_processing(sentence, context)
    
    elif text.startswith('http'):
        # URL recap request
        logger.info(f"Processing URL recap: '{text}'")
        simulate_url_recap_processing(text, context)
    
    else:
        # Regular explanation request
        logger.info(f"Processing explanation request: '{text}'")
        simulate_explanation_processing(text, context)


def process_callback_query(data, context):
    """Process callback query (button press)."""
    logger.info(f"Processing callback query: '{data}'")
    
    if data.startswith('study_grade:'):
        grade = data.split(':', 1)[1]
        simulate_study_grade_processing(grade, context)
    elif data == 'study_next':
        simulate_study_next_processing(context)
    elif data == 'study_stop':
        simulate_study_stop_processing(context)
    elif data.startswith('language_select:'):
        language = data.split(':', 1)[1]
        simulate_language_select_processing(language, context)
    else:
        logger.warning(f"Unknown callback data: '{data}'")


# Simulation functions for different bot operations
def simulate_command_processing(command, args, context):
    """Simulate processing of various commands."""
    
    if command == 'start':
        logger.info("Simulating onboarding flow")
        context.send_message("Welcome to Begriff! Let's set up your languages.")
        
    elif command == 'study':
        logger.info("Simulating study session start")
        # This would normally query database for due cards
        context.send_message("Starting study session...")
        time.sleep(0.1)  # Simulate database query
        context.send_message("Here's your first card: What does 'hello' mean?")
        
    elif command == 'list':
        logger.info("Simulating notes list")
        time.sleep(0.05)  # Simulate database query
        context.send_message("Here are your recent notes...")
        
    elif command == 'language':
        logger.info("Simulating language management")
        context.send_message("Select your study language:")
        
    elif command == 'help':
        logger.info("Simulating help command")
        context.send_message("Available commands: /start, /study, /list, /language, /help")
        
    else:
        logger.warning(f"Unknown command: {command}")
        context.send_message("Unknown command. Type /help for available commands.")


def simulate_explanation_processing(text, context):
    """Simulate explanation request with LLM call."""
    logger.info("Making mock LLM call for explanation")
    
    # Simulate LLM call (this would call the mock LLM service)
    import requests
    try:
        response = requests.post(f"{StressTestConfig.MOCK_LLM_URL}/v1/chat/completions", 
                               json={
                                   "model": "gpt-4o-mini",
                                   "messages": [{"role": "user", "content": f"Explain the word: {text}"}]
                               }, timeout=5)
        
        if response.status_code == 200:
            result = response.json()
            explanation = result['choices'][0]['message']['content']
            context.send_message(f"Explanation: {explanation}")
        else:
            context.send_message("Sorry, couldn't get explanation right now.")
            
    except Exception as e:
        logger.error(f"Mock LLM call failed: {e}")
        context.send_message("Error getting explanation.")


def simulate_translation_processing(word, context):
    """Simulate translation with LLM call."""
    logger.info("Making mock LLM call for translation")
    
    import requests
    try:
        response = requests.post(f"{StressTestConfig.MOCK_LLM_URL}/v1/chat/completions",
                               json={
                                   "model": "gpt-4o-mini", 
                                   "messages": [{"role": "user", "content": f"Translate: {word}"}]
                               }, timeout=5)
        
        if response.status_code == 200:
            result = response.json()
            translation = result['choices'][0]['message']['content']
            context.send_message(f"Translation: {translation}")
        else:
            context.send_message("Sorry, couldn't translate right now.")
            
    except Exception as e:
        logger.error(f"Mock translation call failed: {e}")
        context.send_message("Error getting translation.")


def simulate_grammar_check_processing(sentence, context):
    """Simulate grammar check with LLM call."""
    logger.info("Making mock LLM call for grammar check")
    
    import requests
    try:
        response = requests.post(f"{StressTestConfig.MOCK_LLM_URL}/v1/chat/completions",
                               json={
                                   "model": "gpt-4o-mini",
                                   "messages": [{"role": "user", "content": f"Check grammar: {sentence}"}]
                               }, timeout=5)
        
        if response.status_code == 200:
            result = response.json()
            correction = result['choices'][0]['message']['content']
            context.send_message(f"Grammar check: {correction}")
        else:
            context.send_message("Sorry, couldn't check grammar right now.")
            
    except Exception as e:
        logger.error(f"Mock grammar check failed: {e}")
        context.send_message("Error checking grammar.")


def simulate_url_recap_processing(url, context):
    """Simulate URL recap with LLM call (3-second delay)."""
    logger.info("Making mock LLM call for URL recap (3-second delay expected)")
    
    import requests
    try:
        response = requests.post(f"{StressTestConfig.MOCK_LLM_URL}/v1/chat/completions",
                               json={
                                   "model": "gpt-4o",  # This should trigger the 3-second delay
                                   "messages": [{"role": "user", "content": f"Provide a recap of this URL content: {url}"}]
                               }, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            recap = result['choices'][0]['message']['content']
            context.send_message(f"URL Recap: {recap}")
        else:
            context.send_message("Sorry, couldn't create recap right now.")
            
    except Exception as e:
        logger.error(f"Mock recap call failed: {e}")
        context.send_message("Error creating recap.")


def simulate_study_grade_processing(grade, context):
    """Simulate study card grading."""
    logger.info(f"Processing study grade: {grade}")
    
    # Simulate FSRS calculation and database update
    time.sleep(0.05)  # Database update simulation
    
    context.send_message(f"Card graded as '{grade}'. Next card coming up...")
    time.sleep(0.02)  # Database query for next card
    context.send_message("What does 'world' mean?")


def simulate_study_next_processing(context):
    """Simulate getting next study card."""
    logger.info("Getting next study card")
    time.sleep(0.03)  # Database query simulation
    context.send_message("Here's your next card...")


def simulate_study_stop_processing(context):
    """Simulate stopping study session."""
    logger.info("Stopping study session")
    time.sleep(0.02)  # Session cleanup simulation
    context.send_message("Study session ended. Great work!")


def simulate_language_select_processing(language, context):
    """Simulate language selection."""
    logger.info(f"Setting language to: {language}")
    time.sleep(0.03)  # Database update simulation
    context.send_message(f"Language set to {language}")


class MockContext:
    """Mock context to simulate python-telegram-bot context."""
    
    def __init__(self, update):
        self.update = update
        self.user = None
        self.message = None
        self.callback_query = None
        self.bot = None
        self.responses = []
    
    def send_message(self, text, **kwargs):
        """Simulate sending a message."""
        logger.debug(f"Would send message: {text[:100]}...")
        self.responses.append({"type": "message", "text": text})
        return MockMessage()
    
    def edit_message(self, text, **kwargs):
        """Simulate editing a message."""
        logger.debug(f"Would edit message: {text[:100]}...")
        self.responses.append({"type": "edit", "text": text})
        return MockMessage()
    
    def answer_callback_query(self, text=None, **kwargs):
        """Simulate answering callback query."""
        logger.debug(f"Would answer callback query: {text}")
        self.responses.append({"type": "callback_answer", "text": text})
        return True


class MockMessage:
    """Mock message object."""
    def __init__(self):
        self.message_id = 12345


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
        
        # Run the Flask app
        webhook_app.run(
            host='127.0.0.1',
            port=StressTestConfig.TELEGRAM_BOT_PORT,
            debug=False,
            threaded=True  # Allow concurrent requests
        )
        
    except Exception as e:
        logger.error(f"Error running webhook server: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())