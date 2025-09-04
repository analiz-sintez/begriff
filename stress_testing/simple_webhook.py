#!/usr/bin/env python3
"""
Simple webhook server that just accepts POST requests and returns OK.
This is for testing the load generation without complex bot logic.
"""

import json
import time
import random
from flask import Flask, request, jsonify
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Track request statistics
request_count = 0
start_time = time.time()

@app.route('/telegram', methods=['POST'])
def handle_webhook():
    """Handle incoming webhook requests."""
    global request_count
    request_count += 1
    
    try:
        # Get the JSON data
        update_data = request.get_json()
        
        # Log basic info about the request
        if update_data:
            update_id = update_data.get('update_id', 'unknown')
            
            # Extract message info
            if 'message' in update_data:
                user_id = update_data['message'].get('from', {}).get('id', 'unknown')
                text = update_data['message'].get('text', '')[:50]
                logger.info(f"Request #{request_count}: Update {update_id}, User {user_id}, Text: '{text}'")
            elif 'callback_query' in update_data:
                user_id = update_data['callback_query'].get('from', {}).get('id', 'unknown')
                data = update_data['callback_query'].get('data', '')
                logger.info(f"Request #{request_count}: Update {update_id}, User {user_id}, Callback: '{data}'")
            else:
                logger.info(f"Request #{request_count}: Update {update_id}, Unknown type")
        
        # Simulate some processing time (very small to test basic throughput)
        time.sleep(random.uniform(0.01, 0.05))  # 10-50ms random delay
        
        # Return success
        return jsonify({"ok": True})
        
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    uptime = time.time() - start_time
    return jsonify({
        "status": "healthy",
        "service": "simple-webhook",
        "uptime_seconds": round(uptime, 2),
        "requests_handled": request_count,
        "requests_per_second": round(request_count / uptime if uptime > 0 else 0, 2)
    })


@app.route('/stats', methods=['GET'])
def get_stats():
    """Get request statistics."""
    uptime = time.time() - start_time
    return jsonify({
        "requests_total": request_count,
        "uptime_seconds": round(uptime, 2),
        "requests_per_second": round(request_count / uptime if uptime > 0 else 0, 2),
        "start_time": start_time
    })


if __name__ == '__main__':
    print("=== Simple Webhook Server for Basic Load Testing ===")
    print("This server just accepts webhook calls and logs them")
    print("Listening on: http://127.0.0.1:8000")
    print("Webhook endpoint: /telegram")
    print("Health check: /health")
    print("Statistics: /stats")
    print("Ready for load testing!")
    
    app.run(host='127.0.0.1', port=8000, debug=False)