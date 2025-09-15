#!/usr/bin/env python3
"""
Mock Telegram Bot API server that mimics the real Telegram API.
This allows the bot to make real API calls locally without network errors.
"""

import json
import time
import logging
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock bot info
MOCK_BOT = {
    "id": 123456789,
    "is_bot": True,
    "first_name": "BegriffBot",
    "username": "begriffbot",
    "can_join_groups": True,
    "can_read_all_group_messages": False,
    "supports_inline_queries": False
}

# Storage for mock responses
message_counter = 1000


@app.route('/bot<token>/getMe', methods=['GET', 'POST'])
def get_me(token):
    """Mock getMe endpoint."""
    logger.debug(f"getMe called for token: {token[:10]}...")
    return jsonify({
        "ok": True,
        "result": MOCK_BOT
    })


@app.route('/bot<token>/sendMessage', methods=['POST'])
def send_message(token):
    """Mock sendMessage endpoint."""
    global message_counter
    message_counter += 1
    
    # Handle both JSON and form data (Telegram bot library can send either)
    if request.is_json:
        data = request.get_json()
    else:
        # Convert form data to dict for consistency
        data = request.form.to_dict()
    
    if not data:
        return jsonify({"ok": False, "error_code": 400, "description": "Bad Request"}), 400
    
    chat_id = data.get('chat_id')
    text = data.get('text', '')
    
    logger.debug(f"sendMessage to chat {chat_id}: {text[:50]}...")
    
    # Return a mock message
    mock_message = {
        "message_id": message_counter,
        "from": MOCK_BOT,
        "chat": {
            "id": chat_id,
            "type": "private"
        },
        "date": int(time.time()),
        "text": text
    }
    
    return jsonify({
        "ok": True,
        "result": mock_message
    })


@app.route('/bot<token>/editMessageText', methods=['POST'])
def edit_message_text(token):
    """Mock editMessageText endpoint."""
    # Handle both JSON and form data
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    if not data:
        return jsonify({"ok": False, "error_code": 400, "description": "Bad Request"}), 400
    
    text = data.get('text', '')
    logger.debug(f"editMessageText: {text[:50]}...")
    
    # Return success
    return jsonify({
        "ok": True,
        "result": True
    })


@app.route('/bot<token>/answerCallbackQuery', methods=['POST'])
def answer_callback_query(token):
    """Mock answerCallbackQuery endpoint."""
    # Handle both JSON and form data
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    logger.debug(f"answerCallbackQuery: {data}")
    
    return jsonify({
        "ok": True,
        "result": True
    })


@app.route('/bot<token>/sendPhoto', methods=['POST'])
def send_photo(token):
    """Mock sendPhoto endpoint."""
    global message_counter
    message_counter += 1
    
    # Handle both form-data and JSON
    if request.content_type and 'application/json' in request.content_type:
        data = request.get_json()
        chat_id = data.get('chat_id')
        caption = data.get('caption', '')
    else:
        chat_id = request.form.get('chat_id')
        caption = request.form.get('caption', '')
    
    logger.debug(f"sendPhoto to chat {chat_id} with caption: {caption[:50]}...")
    
    mock_message = {
        "message_id": message_counter,
        "from": MOCK_BOT,
        "chat": {
            "id": int(chat_id) if chat_id else 12345,
            "type": "private"
        },
        "date": int(time.time()),
        "photo": [
            {
                "file_id": f"mock_photo_{message_counter}",
                "file_unique_id": f"mock_unique_{message_counter}",
                "width": 512,
                "height": 512,
                "file_size": 1024
            }
        ]
    }
    
    if caption:
        mock_message["caption"] = caption
    
    return jsonify({
        "ok": True,
        "result": mock_message
    })


@app.route('/bot<token>/<path:method>', methods=['GET', 'POST'])
def catch_all(token, method):
    """Catch-all for any other Telegram API methods."""
    logger.debug(f"Mock API call: {method} for token {token[:10]}...")
    
    # Return a generic success response
    return jsonify({
        "ok": True,
        "result": True
    })


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy", 
        "service": "mock-telegram-api",
        "bot": MOCK_BOT
    })


if __name__ == '__main__':
    print("Starting Mock Telegram Bot API on http://localhost:8003")
    print("Bot info:", MOCK_BOT)
    print("All Telegram API calls will be handled locally")
    app.run(host='127.0.0.1', port=8003, debug=False)