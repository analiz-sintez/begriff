#!/usr/bin/env python3
"""
Modified version of run_telegram.py for webhook-only stress testing.
Forces the bot to run in webhook mode for local testing.
"""

import sys
import os
import logging
from pathlib import Path

# Add the parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import StressTestConfig

# Apply test environment before importing the app
StressTestConfig.apply_test_environment()

from time import sleep
from telegram import Update
from telegram.ext import Application
from nachricht import setup_logging

setup_logging()

from nachricht.bus import Bus
from nachricht.messenger import Router
from nachricht.messenger.telegram import attach_bus, attach_router

# Import after environment is set
from app import bus, router, create_app, Config

logger = logging.getLogger(__name__)


def create_bot(token: str, router: Router, bus: Bus) -> Application:
    """
    Create and configure the Telegram bot application
    with command and callback handlers.
    """
    application = Application.builder().token(token).build()
    attach_router(router, application)
    attach_bus(bus, application)
    return application


def main():
    """Run the bot in webhook mode for stress testing."""
    
    print("=== Begriff Bot Webhook Mode for Stress Testing ===")
    print(f"Webhook URL: {StressTestConfig.TELEGRAM_WEBHOOK_URL}")
    print(f"Port: {StressTestConfig.TELEGRAM_BOT_PORT}")
    
    # Check database exists (should be initialized by startup script)
    from pathlib import Path
    project_dir = Path(__file__).parent.parent
    db_path = project_dir / "data" / "test_database.sqlite"
    
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        print("Please run the initialization script first")
        return 1
    
    print(f"✓ Using database: {db_path}")
    
    # Set absolute database URL
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.absolute()}"
    
    # Create Flask app with test configuration
    app = create_app()
    
    # Override LLM configuration to point to mock service
    from app.config import Config as AppConfig
    AppConfig.LLM.update({
        "host": f"{StressTestConfig.MOCK_LLM_URL}/v1",
        "api_key": "mock_api_key"
    })
    
    print(f"LLM endpoint: {AppConfig.LLM['host']}")
    
    # Get bot token (use dummy for stress testing)
    token = Config.TELEGRAM["bot_token"]
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is not set, using dummy token for stress testing")
        print("WARNING: Using dummy token for stress testing")
        token = "123456789:DUMMY_TOKEN_FOR_STRESS_TESTING"
    
    bot = create_bot(token, router, bus)
    logger.info("Telegram bot initialized for webhook mode.")
    
    # Force webhook mode for testing
    webhook_url = StressTestConfig.TELEGRAM_WEBHOOK_URL
    secret_token = "test_secret_token"
    
    print("Starting webhook server...")
    print(f"Listening on: 127.0.0.1:{StressTestConfig.TELEGRAM_BOT_PORT}")
    print(f"Webhook endpoint: /telegram")
    print("Ready for stress testing!")
    
    try:
        with app.app_context():
            bot.run_webhook(
                listen="127.0.0.1",
                port=StressTestConfig.TELEGRAM_BOT_PORT,
                url_path="telegram",
                secret_token=secret_token,
                webhook_url=webhook_url,
                allowed_updates=Update.ALL_TYPES,
            )
    except KeyboardInterrupt:
        print("\nShutting down webhook server...")
        return 0
    except Exception as e:
        logger.error(f"Error running webhook: {e}")
        return 1


if __name__ == "__main__":
    exit_code = 0
    for attempt in range(3):
        try:
            exit_code = main()
            break
        except RuntimeError as e:
            logger.error("Error: %s, retrying...", e)
            sleep(3)
            exit_code = 1
    
    sys.exit(exit_code)