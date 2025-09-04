#!/usr/bin/env python3
"""
Mock image generation service that mimics Vertex AI API with configurable delays.
Provides endpoints for image generation with Gaussian random delays.
"""

import json
import random
import time
import base64
import io
from typing import Dict, Any

from flask import Flask, request, jsonify
import numpy as np
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# Default delay configuration (3 seconds mean, 0.1 std)
IMAGE_DELAY = {"mean": 3.0, "std": 0.1}


def get_image_delay() -> float:
    """
    Get delay for image generation using Gaussian distribution.
    Returns delay in seconds.
    """
    delay = np.random.normal(IMAGE_DELAY["mean"], IMAGE_DELAY["std"])
    return max(0.5, delay)  # Ensure minimum delay of 500ms


def generate_mock_image(prompt: str) -> str:
    """
    Generate a simple mock image and return as base64 encoded string.
    Creates a colored rectangle with the prompt text.
    """
    # Create a simple image
    width, height = 512, 512
    
    # Random background color
    bg_color = (
        random.randint(100, 255),
        random.randint(100, 255), 
        random.randint(100, 255)
    )
    
    # Create image
    img = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # Add prompt text (truncated if too long)
    text = prompt[:50] + "..." if len(prompt) > 50 else prompt
    
    try:
        # Try to use a font, fallback to default if not available
        font = ImageFont.load_default()
    except:
        font = None
    
    # Draw text in center
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    text_x = (width - text_width) // 2
    text_y = (height - text_height) // 2
    
    draw.text((text_x, text_y), text, fill=(0, 0, 0), font=font)
    
    # Add a simple border
    draw.rectangle([(10, 10), (width-10, height-10)], outline=(0, 0, 0), width=3)
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return base64.b64encode(buffer.read()).decode('utf-8')


@app.route('/v1/projects/<project_id>/locations/<location>/publishers/google/models/imagen-4.0-generate-preview-06-06:predict', methods=['POST'])
def generate_image(project_id: str, location: str):
    """Mock Vertex AI image generation endpoint."""
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400
        
        # Extract prompt from the request
        instances = data.get("instances", [])
        if not instances:
            return jsonify({"error": "No instances provided"}), 400
        
        instance = instances[0]
        prompt = instance.get("prompt", "default image")
        
        print(f"Generating image for prompt: '{prompt[:50]}...'")
        
        # Apply delay
        delay = get_image_delay()
        print(f"Applying {delay:.3f}s delay for image generation")
        time.sleep(delay)
        
        # Generate mock image
        image_b64 = generate_mock_image(prompt)
        
        # Return in Vertex AI format
        response = {
            "predictions": [
                {
                    "bytesBase64Encoded": image_b64,
                    "mimeType": "image/png"
                }
            ]
        }
        
        return jsonify(response)
    
    except Exception as e:
        print(f"Error generating image: {e}")
        return jsonify({
            "error": {
                "message": str(e),
                "code": "INTERNAL",
                "status": "INTERNAL"
            }
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "mock-image"})


@app.route('/config', methods=['POST'])
def update_config():
    """Update delay configuration."""
    global IMAGE_DELAY
    
    try:
        new_config = request.get_json()
        if new_config and "delay" in new_config:
            IMAGE_DELAY.update(new_config["delay"])
            return jsonify({"status": "updated", "delay": IMAGE_DELAY})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    
    return jsonify({"error": "Invalid configuration"}), 400


if __name__ == '__main__':
    print("Starting Mock Image Service on http://localhost:8002")
    print("Delay configuration:", IMAGE_DELAY)
    app.run(host='127.0.0.1', port=8002, debug=False)