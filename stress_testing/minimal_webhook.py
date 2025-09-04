#!/usr/bin/env python3
"""
Minimal webhook server that handles Telegram updates without authentication.
This bypasses the python-telegram-bot authentication and runs just the webhook endpoint.
"""

import sys
import os
import json
import logging
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
from nachricht.messenger.telegram import process_update
from telegram import Update

def create_minimal_webhook_app():
    """Create a minimal Flask app that just handles webhook endpoints."""
    
    # Create the main app to initialize database and services
    main_app = create_app()
    
    # Create a simple Flask app for webhook handling
    webhook_app = Flask(__name__)
    
    @webhook_app.route('/telegram', methods=['POST'])
    def handle_webhook():
        """Handle incoming Telegram webhooks."""
        try:
            # Get JSON data
            update_data = request.get_json()
            if not update_data:
                logger.warning("No JSON data in request")
                return jsonify({"ok": False, "error": "No JSON data"}), 400
            
            logger.debug(f"Received update: {json.dumps(update_data, indent=2)}")
            
            # Create Telegram Update object
            try:
                update = Update.de_json(update_data, None)  # No bot object needed for parsing
                if not update:
                    logger.warning("Failed to parse update")
                    return jsonify({"ok": False, "error": "Invalid update format"}), 400
            except Exception as e:
                logger.error(f"Error parsing update: {e}")
                return jsonify({"ok": False, "error": f"Parse error: {str(e)}"}), 400
            
            # Process the update within the main app context
            with main_app.app_context():
                try:
                    # Use nachricht's routing to process the update
                    # This simulates what python-telegram-bot would do
                    process_telegram_update(update)
                    
                    logger.info(f"Successfully processed update {update.update_id}")
                    return jsonify({"ok": True})
                    
                except Exception as e:
                    logger.error(f"Error processing update: {e}")
                    return jsonify({"ok": False, "error": f"Processing error: {str(e)}"}), 500
                    
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return jsonify({"ok": False, "error": f"Webhook error: {str(e)}"}), 500
    
    @webhook_app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint."""
        return jsonify({"status": "healthy", "service": "webhook"})
    
    return webhook_app, main_app


def process_telegram_update(update):
    """Process a Telegram update using nachricht routing."""
    try:
        # Extract user and message info
        user = None
        message = None
        callback_query = None
        
        if update.message:
            message = update.message
            user = message.from_user
        elif update.callback_query:
            callback_query = update.callback_query
            user = callback_query.from_user
            message = callback_query.message
        
        if not user:
            logger.warning("No user found in update")
            return
        
        # Create a simple context object for routing
        context = SimpleContext(update, user, message, callback_query)
        
        # Try to route the message through nachricht
        if message and message.text:
            router.route_message(message.text, context)
        elif callback_query and callback_query.data:
            router.route_callback_query(callback_query.data, context)
        else:
            logger.warning("No text or callback data to route")
            
    except Exception as e:
        logger.error(f"Error in process_telegram_update: {e}")
        raise


class SimpleContext:
    """Simple context object to simulate python-telegram-bot context."""
    
    def __init__(self, update, user, message, callback_query):
        self.update = update
        self.user = user
        self.message = message
        self.callback_query = callback_query
        self.bot = None  # We don't have a real bot
    
    def send_message(self, text, **kwargs):
        """Simulate sending a message (just log it)."""
        logger.info(f"Would send message to {self.user.id}: {text[:100]}...")
        return MockMessage()
    
    def edit_message(self, text, **kwargs):
        """Simulate editing a message."""
        logger.info(f"Would edit message for {self.user.id}: {text[:100]}...")
        return MockMessage()
    
    def answer_callback_query(self, text=None, **kwargs):
        """Simulate answering callback query."""
        logger.info(f"Would answer callback query for {self.user.id}: {text}")
        return True


class MockMessage:
    """Mock message object."""
    def __init__(self):
        self.message_id = 12345
        self.date = None


def main():
    """Run the minimal webhook server."""
    
    print("=== Begriff Minimal Webhook Server for Stress Testing ===")
    print(f"Port: {StressTestConfig.TELEGRAM_BOT_PORT}")
    
    # Check database exists
    project_dir = Path(__file__).parent.parent
    db_path = project_dir / "data" / "test_database.sqlite"
    
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1
    
    print(f"✓ Using database: {db_path}")
    
    # Create webhook app
    try:
        webhook_app, main_app = create_minimal_webhook_app()
        
        print("✓ Webhook server initialized")
        print(f"Listening on: 127.0.0.1:{StressTestConfig.TELEGRAM_BOT_PORT}")
        print(f"Webhook endpoint: /telegram")
        print("Ready for stress testing!")
        
        # Run the Flask app
        webhook_app.run(
            host='127.0.0.1',
            port=StressTestConfig.TELEGRAM_BOT_PORT,
            debug=False
        )
        
    except Exception as e:
        logger.error(f"Error running webhook server: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())