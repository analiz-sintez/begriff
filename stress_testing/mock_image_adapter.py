#!/usr/bin/env python3
"""
Mock image service adapter that replaces Vertex AI calls with mock service calls.
This module monkey-patches the real image service to use our mock HTTP service.
"""

import os
import hashlib
import logging
import asyncio
import requests
import base64
from asyncio import to_thread
from pathlib import Path

from config import StressTestConfig

logger = logging.getLogger(__name__)


def mock_generate_image(description: str, force: bool = False) -> str:
    """
    Mock version of generate_image that calls our mock HTTP service instead of Vertex AI.
    
    Args:
        description: text content used for image generation.
        force: regenerate image even if it already exists.
    
    Returns:
        Path to the generated image file.
    """
    logger.info(f"Mock image generation for description: '{description[:50]}...'")
    
    # Create a hash of the description for filename
    description_hash = hashlib.md5(description.encode()).hexdigest()[:8]
    
    # Ensure images directory exists
    images_dir = Path("data/images")
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if image already exists and force is False
    image_path = images_dir / f"{description_hash}.png"
    if image_path.exists() and not force:
        logger.info(f"Image already exists: {image_path}")
        return str(image_path)
    
    try:
        # Call our mock image service
        payload = {
            "instances": [
                {
                    "prompt": description,
                    "sampleCount": 1
                }
            ]
        }
        
        # Use the same endpoint format as real Vertex AI
        mock_endpoint = f"{StressTestConfig.MOCK_IMAGE_URL}/v1/projects/mock_project/locations/us-central1/publishers/google/models/imagen-4.0-generate-preview-06-06:predict"
        
        logger.debug(f"Calling mock image service at: {mock_endpoint}")
        response = requests.post(mock_endpoint, json=payload, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            predictions = result.get("predictions", [])
            
            if predictions:
                # Extract base64 image data
                image_b64 = predictions[0].get("bytesBase64Encoded")
                
                if image_b64:
                    # Decode and save the image
                    image_data = base64.b64decode(image_b64)
                    
                    with open(image_path, "wb") as f:
                        f.write(image_data)
                    
                    logger.info(f"Mock image saved to: {image_path}")
                    return str(image_path)
                else:
                    logger.error("No image data in mock response")
            else:
                logger.error("No predictions in mock response")
        else:
            logger.error(f"Mock image service returned {response.status_code}: {response.text}")
    
    except Exception as e:
        logger.error(f"Error calling mock image service: {e}")
        
    # Return a placeholder path if generation fails
    placeholder_path = images_dir / f"placeholder_{description_hash}.png"
    logger.warning(f"Using placeholder image: {placeholder_path}")
    return str(placeholder_path)


async def async_mock_generate_image(description: str, force: bool = False) -> str:
    """Async wrapper for mock_generate_image."""
    return await to_thread(mock_generate_image, description, force)


def patch_image_service():
    """
    Monkey-patch the real image service to use our mock service.
    This should be called before the app starts processing requests.
    """
    try:
        import sys
        from app.image import service as image_service
        
        # Replace the generate_image function
        original_generate_image = image_service.generate_image
        image_service.generate_image = async_mock_generate_image
        
        logger.info("Successfully patched image service to use mock service")
        
        # Also patch vertexai to avoid import issues
        import vertexai
        from unittest.mock import MagicMock
        
        # Mock the ImageGenerationModel
        mock_model = MagicMock()
        mock_model.generate_images.return_value.images = []
        
        # Create a mock ImageGenerationModel class
        class MockImageGenerationModel:
            @classmethod
            def from_pretrained(cls, model_name):
                logger.debug(f"Mock ImageGenerationModel.from_pretrained called with {model_name}")
                return mock_model
        
        # Patch vertexai modules
        if 'vertexai.preview.vision_models' in sys.modules:
            sys.modules['vertexai.preview.vision_models'].ImageGenerationModel = MockImageGenerationModel
        
        logger.info("Successfully patched Vertex AI ImageGenerationModel")
        
    except ImportError as e:
        logger.warning(f"Could not patch image service: {e}")
    except Exception as e:
        logger.error(f"Error patching image service: {e}")