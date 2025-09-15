#!/bin/bash

# Start all services for stress testing
# Usage: ./start_services.sh [clean]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Begriff Stress Testing Service Starter ==="
echo "Project directory: $PROJECT_DIR"
echo "Script directory: $SCRIPT_DIR"

# Clean up function
cleanup() {
    echo "Cleaning up processes..."
    pkill -f "mock_llm_service.py" || true
    pkill -f "mock_image_service.py" || true
    pkill -f "mock_telegram_api.py" || true
    pkill -f "run_bot_webhook.py" || true
    pkill -f "real_webhook.py" || true
    pkill -f "simple_webhook.py" || true
    pkill -f "minimal_webhook.py" || true
    sleep 2
    
    # Force kill anything still using our ports
    for port in 8001 8002 8000 8003; do
        pid=$(lsof -t -i :$port 2>/dev/null || true)
        if [ ! -z "$pid" ]; then
            echo "Force killing process $pid using port $port"
            kill -9 $pid || true
        fi
    done
}

# Handle cleanup on exit
trap cleanup EXIT

# Clean existing processes if requested
if [ "$1" = "clean" ]; then
    echo "Cleaning existing processes..."
    cleanup
    exit 0
fi

# Change to project directory
cd "$PROJECT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "ERROR: Virtual environment not found. Please run 'make venv' first."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if required packages are installed
python -c "import locust" || {
    echo "Installing locust..."
    pip install locust
}

echo "Starting mock services..."

# Start mock LLM service
echo "Starting Mock LLM Service on port 8001..."
python "$SCRIPT_DIR/mock_llm_service.py" &
LLM_PID=$!
sleep 2

# Check if LLM service started
if ! curl -s http://localhost:8001/health > /dev/null; then
    echo "ERROR: Mock LLM service failed to start"
    kill $LLM_PID || true
    exit 1
fi
echo "✓ Mock LLM service started (PID: $LLM_PID)"

# Start mock image service  
echo "Starting Mock Image Service on port 8002..."
python "$SCRIPT_DIR/mock_image_service.py" &
IMAGE_PID=$!
sleep 2

# Check if image service started
if ! curl -s http://localhost:8002/health > /dev/null; then
    echo "ERROR: Mock Image service failed to start"
    kill $LLM_PID $IMAGE_PID || true
    exit 1
fi
echo "✓ Mock Image service started (PID: $IMAGE_PID)"

# Start mock Telegram API service
echo "Starting Mock Telegram API Service on port 8003..."
python "$SCRIPT_DIR/mock_telegram_api.py" &
TELEGRAM_API_PID=$!
sleep 2

# Check if Telegram API service started
if ! curl -s http://localhost:8003/health > /dev/null; then
    echo "ERROR: Mock Telegram API service failed to start"
    kill $LLM_PID $IMAGE_PID $TELEGRAM_API_PID || true
    exit 1
fi
echo "✓ Mock Telegram API service started (PID: $TELEGRAM_API_PID)"

# Ensure data directory exists
mkdir -p data

# Initialize test database properly
echo "Initializing test database..."
python "$SCRIPT_DIR/init_test_db.py"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to initialize test database"
    cleanup
    exit 1
fi

# Start real webhook server with bot logic and mock services
echo "Starting Real Webhook Server with Bot Logic on port 8000..."
python "$SCRIPT_DIR/real_webhook.py" &
BOT_PID=$!
sleep 3

# Check if webhook started
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✓ Webhook server started (PID: $BOT_PID)"
else
    echo "ERROR: Webhook server failed to start"
    kill $LLM_PID $IMAGE_PID $TELEGRAM_API_PID $BOT_PID || true
    exit 1
fi

echo ""
echo "=== All services started successfully! ==="
echo "Mock LLM Service: http://localhost:8001"
echo "Mock Image Service: http://localhost:8002"
echo "Mock Telegram API: http://localhost:8003"  
echo "Telegram Bot Webhook: http://localhost:8000/telegram"
echo ""
echo "To run stress tests:"
echo "  cd $SCRIPT_DIR"
echo "  locust -f locustfile.py --host=http://localhost:8000"
echo ""
echo "Or use the run_stress_test.sh script for automated scenarios"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for user interrupt
wait