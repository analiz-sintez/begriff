#!/usr/bin/env python3
"""
Configuration for stress testing setup.
"""

import os


class StressTestConfig:
    """Configuration for stress test environment."""
    
    # Service ports
    MOCK_LLM_PORT = 8001
    MOCK_IMAGE_PORT = 8002
    TELEGRAM_BOT_PORT = 8000
    MOCK_TELEGRAM_API_PORT = 8003
    
    # Service URLs
    MOCK_LLM_URL = f"http://localhost:{MOCK_LLM_PORT}"
    MOCK_IMAGE_URL = f"http://localhost:{MOCK_IMAGE_PORT}"
    TELEGRAM_WEBHOOK_URL = f"http://localhost:{TELEGRAM_BOT_PORT}/telegram"
    MOCK_TELEGRAM_API_URL = f"http://localhost:{MOCK_TELEGRAM_API_PORT}"
    
    # Environment variables to override for testing
    @classmethod
    def get_test_env_vars(cls):
        """Get test environment variables with dynamic database path."""
        import os
        from pathlib import Path
        
        # Get absolute database path
        project_dir = Path(__file__).parent.parent
        db_path = project_dir / "data" / "test_database.sqlite"
        
        return {
            # Point to mock services instead of real APIs
            "OPENAI_API_KEY": "mock_api_key",
            
            # Telegram configuration for stress testing
            "TELEGRAM_BOT_TOKEN": "123456789:DUMMY_TOKEN_FOR_STRESS_TESTING",
            "TELEGRAM_WEBHOOK_URL": cls.TELEGRAM_WEBHOOK_URL,
            "TELEGRAM_WEBHOOK_SECRET_TOKEN": "test_secret_token",
            "TELEGRAM_BOT_API_URL": cls.MOCK_TELEGRAM_API_URL,
            
            # Disable real image generation
            "VERTEX_AI_PROJECT_ID": "mock_project",
            
            # Use test database with absolute path
            "DATABASE_URL": f"sqlite:///{db_path.absolute()}",
        }
    
    # Locust test scenarios (doubling users as specified)
    SCENARIOS = [
        {"users": 10, "spawn_rate": 2, "duration": "30s", "name": "baseline"},
        {"users": 20, "spawn_rate": 4, "duration": "30s", "name": "2x_load"},
        {"users": 40, "spawn_rate": 8, "duration": "30s", "name": "4x_load"},
        {"users": 80, "spawn_rate": 16, "duration": "30s", "name": "8x_load"},
        {"users": 160, "spawn_rate": 32, "duration": "30s", "name": "16x_load"},
    ]
    
    @classmethod
    def apply_test_environment(cls):
        """Apply test environment variables."""
        test_vars = cls.get_test_env_vars()
        for key, value in test_vars.items():
            os.environ[key] = value
            print(f"Set {key}={value}")


class MockServiceConfig:
    """Configuration for mock services."""
    
    # LLM Service delays (in seconds)
    LLM_DELAYS = {
        "recap": {"mean": 3.0, "std": 0.1},
        "explanation": {"mean": 1.0, "std": 0.1},
        "default": {"mean": 1.0, "std": 0.1},
    }
    
    # Image service delay (in seconds)
    IMAGE_DELAY = {"mean": 3.0, "std": 0.1}
    
    @classmethod
    def get_updated_app_config(cls):
        """Get updated configuration for the main app."""
        return {
            "LLM": {
                "host": StressTestConfig.MOCK_LLM_URL + "/v1",
                "api_key": "mock_api_key",
                "models": {
                    "default": "gpt-4o-mini",
                    "base_form": "gpt-4o-mini", 
                    "explanation": "gpt-4o-mini",
                    "recap": "gpt-4o",  # This should trigger the 3-second delay
                },
            },
            "IMAGE": {
                "enable": True,
                "model": "imagen-4.0-generate-preview-06-06",
                "vertexai_project_id": "mock_project",
                "vertexai_location": "us-central1",
            }
        }