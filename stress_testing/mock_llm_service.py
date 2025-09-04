#!/usr/bin/env python3
"""
Mock LLM service that mimics OpenAI API with configurable delays.
Provides endpoints for chat completions with Gaussian random delays.
"""

import asyncio
import json
import random
import time
from typing import Dict, Any, List

from flask import Flask, request, jsonify
import numpy as np

app = Flask(__name__)

# Default delays (in seconds)
DEFAULT_DELAYS = {
    "recap": {"mean": 3.0, "std": 0.1},
    "explanation": {"mean": 1.0, "std": 0.1},
    "default": {"mean": 1.0, "std": 0.1},
}


def get_delay_for_request(messages: List[Dict[str, Any]]) -> float:
    """
    Determine appropriate delay based on request content.
    Returns delay in seconds using Gaussian distribution.
    """
    # Analyze messages to determine request type
    content = ""
    for message in messages:
        if isinstance(message.get("content"), str):
            content += message["content"].lower()
    
    # Determine request type based on content
    if "recap" in content or "url" in content or "summarize" in content:
        delay_config = DEFAULT_DELAYS["recap"]
    elif "explain" in content or "what does" in content or "meaning" in content:
        delay_config = DEFAULT_DELAYS["explanation"]
    else:
        delay_config = DEFAULT_DELAYS["default"]
    
    # Generate Gaussian random delay
    delay = np.random.normal(delay_config["mean"], delay_config["std"])
    return max(0.1, delay)  # Ensure minimum delay of 100ms


def generate_mock_response(messages: List[Dict[str, Any]], model: str) -> Dict[str, Any]:
    """Generate a mock response similar to OpenAI API format."""
    
    # Simple response generation based on last message
    last_message = messages[-1]["content"] if messages else "Hello"
    
    if "recap" in last_message.lower():
        response_text = f"This is a mock recap of the content. The main points are: 1) Mock point one 2) Mock point two 3) Mock conclusion."
    elif "explain" in last_message.lower():
        response_text = f"Mock explanation: This word means something specific in the context provided."
    else:
        response_text = f"Mock response to: {last_message[:50]}..."
    
    return {
        "id": f"chatcmpl-mock-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": len(str(messages)) // 4,  # Rough estimate
            "completion_tokens": len(response_text) // 4,
            "total_tokens": (len(str(messages)) + len(response_text)) // 4
        }
    }


@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    """Mock OpenAI chat completions endpoint."""
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400
        
        messages = data.get("messages", [])
        model = data.get("model", "gpt-4o-mini")
        
        # Calculate and apply delay
        delay = get_delay_for_request(messages)
        print(f"Applying {delay:.3f}s delay for request with {len(messages)} messages")
        time.sleep(delay)
        
        # Generate response
        response = generate_mock_response(messages, model)
        
        return jsonify(response)
    
    except Exception as e:
        print(f"Error processing request: {e}")
        return jsonify({
            "error": {
                "message": str(e),
                "type": "mock_error",
                "code": "internal_error"
            }
        }), 500


@app.route('/v1/models', methods=['GET'])
def list_models():
    """Mock models endpoint."""
    return jsonify({
        "object": "list",
        "data": [
            {
                "id": "gpt-4o-mini",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "mock-org"
            },
            {
                "id": "gpt-4o",
                "object": "model", 
                "created": int(time.time()),
                "owned_by": "mock-org"
            }
        ]
    })


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "mock-llm"})


@app.route('/config', methods=['POST'])
def update_config():
    """Update delay configuration."""
    global DEFAULT_DELAYS
    
    try:
        new_config = request.get_json()
        if new_config and "delays" in new_config:
            DEFAULT_DELAYS.update(new_config["delays"])
            return jsonify({"status": "updated", "delays": DEFAULT_DELAYS})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    
    return jsonify({"error": "Invalid configuration"}), 400


if __name__ == '__main__':
    print("Starting Mock LLM Service on http://localhost:8001")
    print("Delay configuration:", DEFAULT_DELAYS)
    app.run(host='127.0.0.1', port=8001, debug=False)