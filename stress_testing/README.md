# Begriff Bot Stress Testing Setup

This directory contains a complete stress testing framework for the Begriff Telegram bot. It simulates user interactions through webhook calls and measures performance under increasing load.

## Architecture

The stress testing setup consists of:

1. **Mock Services**: Replace external APIs to eliminate network dependencies
   - Mock LLM Service (port 8001) - Simulates OpenAI API with configurable delays
   - Mock Image Service (port 8002) - Simulates Vertex AI with configurable delays

2. **Bot Webhook Mode**: Modified bot runner that forces webhook mode for testing
   - Telegram Bot (port 8000) - Receives webhook calls from Locust

3. **Load Testing**: Locust-based scenarios simulating real user behavior
   - Study sessions with card reviews
   - Note taking with explanations and translations  
   - URL recap requests

## Quick Start

### 1. Start All Services
```bash
cd stress_testing
./start_services.sh
```

This will start:
- Mock LLM service on http://localhost:8001
- Mock Image service on http://localhost:8002  
- Telegram bot webhook on http://localhost:8000/telegram

### 2. Run Automated Stress Tests
```bash
./run_stress_test.sh
```

This runs the full test sequence:
- 10 users for 30s
- 20 users for 30s  
- 40 users for 30s
- 80 users for 30s
- 160 users for 30s

Results are saved to `results/` directory with timestamps.

### 3. Manual Testing with Locust UI
```bash
locust -f locustfile.py --host=http://localhost:8000
```

Then open http://localhost:8089 for the Locust web interface.

## Configuration

### Delay Settings
The mock services simulate realistic delays:
- **LLM calls**: 1 second (mean) ± 0.1 second (std)
- **Recap calls**: 3 seconds (mean) ± 0.1 second (std)  
- **Image generation**: 3 seconds (mean) ± 0.1 second (std)

Update delays by modifying `config.py` or sending POST requests to the services:

```bash
# Update LLM delays
curl -X POST http://localhost:8001/config -H "Content-Type: application/json" -d '{
  "delays": {
    "default": {"mean": 2.0, "std": 0.2}
  }
}'

# Update image delays  
curl -X POST http://localhost:8002/config -H "Content-Type: application/json" -d '{
  "delay": {"mean": 5.0, "std": 0.5}
}'
```

### User Scenarios
The test includes 4 user types with different behaviors:

1. **StudySessionUser** (weight=3): Focuses on study sessions
   - Starts study sessions with `/study`
   - Reviews cards and provides grades
   - Continues or stops sessions realistically

2. **NoteTakingUser** (weight=2): Focuses on content creation
   - Asks for explanations: "What does 'word' mean?"
   - Requests translations: "??word"
   - Sends URLs for recaps
   - Uses grammar checking: "!!sentence"

3. **CasualUser** (weight=1): Mixed casual usage
   - Random word lookups
   - Help commands
   - Language management

4. **WikipediaUser** (weight=1): Heavy network load testing (~20% of users)
   - Frequently sends Wikipedia URLs for recap processing
   - Creates real network load with Wikipedia API calls
   - Tests end-to-end performance including external API latency
   - Simulates users who heavily use URL recap features

## Files

- `locustfile.py` - Main Locust test scenarios
- `telegram_utils.py` - Utilities for creating Telegram Update objects
- `mock_llm_service.py` - Mock OpenAI-compatible API server
- `mock_image_service.py` - Mock Vertex AI-compatible image service
- `run_bot_webhook.py` - Modified bot runner for webhook mode
- `config.py` - Configuration and environment setup
- `start_services.sh` - Start all required services
- `run_stress_test.sh` - Run automated test sequence

## Monitoring

### Locust Metrics
- Response times for webhook calls
- Request rates (RPS)
- Error rates
- Percentile distributions

### Service Health Checks
```bash
curl http://localhost:8001/health  # LLM service
curl http://localhost:8002/health  # Image service
```

### Results Analysis
After tests complete, check the `results/` directory:
- `report.html` - Visual Locust report
- `stats_*.csv` - Detailed statistics
- `locust.log` - Test execution logs

## Troubleshooting

### Services Won't Start
1. Check if ports are already in use: `lsof -i :8001 -i :8002 -i :8000`
2. Kill existing processes: `./start_services.sh clean`
3. Restart services: `./start_services.sh`

### Bot Not Responding
1. Verify TELEGRAM_BOT_TOKEN is set in your environment
2. Check if database exists: `ls -la data/test_database.sqlite`
3. Review bot logs in the terminal

### Test Failures
1. Verify all services are healthy before starting tests
2. Check that virtual environment is activated
3. Ensure locust is installed: `pip install locust`

## Advanced Usage

### Custom Test Scenarios
Modify `locustfile.py` to add new user behaviors or adjust weights.

### Different Load Patterns  
Use locust command line options:
```bash
# Constant load
locust -f locustfile.py --host=http://localhost:8000 --users 50 --spawn-rate 10

# Step load increase
locust -f locustfile.py --host=http://localhost:8000 --users 100 --spawn-rate 5 --run-time 60s
```

### Environment Configuration
Set environment variables to modify bot behavior during testing:
```bash
export DATABASE_URL="sqlite:///data/stress_test.db"
export OPENAI_API_KEY="your_real_key"  # To test with real API
```

## Integration with CI/CD

The stress testing can be integrated into CI pipelines:

```bash
# In your CI script
cd stress_testing
./start_services.sh &
SERVICE_PID=$!
sleep 10

# Run lightweight stress test
locust -f locustfile.py --host=http://localhost:8000 --users 5 --spawn-rate 1 --run-time 30s --headless

# Cleanup
kill $SERVICE_PID
```