#!/usr/bin/env python3
"""
Mock language detection to avoid lingua library errors during stress testing.
"""

import logging
from typing import Optional, List, NamedTuple

logger = logging.getLogger(__name__)


class MockConfidenceValue(NamedTuple):
    """Mock confidence value for language detection."""
    language: str
    value: float


def mock_detect_language(text: str, languages: Optional[List[str]] = None) -> MockConfidenceValue:
    """
    Mock language detection that returns a reasonable default.
    Avoids errors from unsupported language strings during stress testing.
    """
    logger.debug(f"Mock language detection for text: '{text[:30]}...' with languages: {languages}")
    
    # Default to English with high confidence
    detected_language = "English"
    confidence = 0.95
    
    # If specific languages provided, prefer the first one
    if languages and languages:
        # Map common language names to full names
        language_map = {
            "en": "English",
            "english": "English", 
            "ru": "Russian",
            "russian": "Russian",
            "es": "Spanish",
            "spanish": "Spanish",
            "de": "German",
            "german": "German",
            "fr": "French",
            "french": "French"
        }
        
        first_lang = languages[0].lower()
        detected_language = language_map.get(first_lang, languages[0].title())
    
    # For stress testing, vary confidence slightly to make it realistic
    import random
    confidence = random.uniform(0.85, 0.99)
    
    logger.debug(f"Mock detected language: {detected_language} (confidence: {confidence:.2f})")
    
    return MockConfidenceValue(language=detected_language, value=confidence)


def patch_language_detection():
    """Patch the real language detection with mock version."""
    try:
        from app.llm import language_detection
        
        # Replace the detect_language function
        original_detect_language = language_detection.detect_language
        language_detection.detect_language = mock_detect_language
        
        logger.info("Successfully patched language detection to use mock version")
        
    except ImportError as e:
        logger.warning(f"Could not patch language detection: {e}")
    except Exception as e:
        logger.error(f"Error patching language detection: {e}")