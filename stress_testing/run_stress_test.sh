#!/bin/bash

# Automated stress testing with progressive load increases
# Implements the 5-step doubling approach specified in requirements

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Begriff Automated Stress Testing ==="
echo "This will run 5 scenarios with doubling user counts:"
echo "1. 10 users for 30s"
echo "2. 20 users for 30s"  
echo "3. 40 users for 30s"
echo "4. 80 users for 30s"
echo "5. 160 users for 30s"
echo ""

# Check if services are running
check_services() {
    local all_running=true
    
    if ! curl -s http://localhost:8001/health > /dev/null; then
        echo "ERROR: Mock LLM service not running on port 8001"
        all_running=false
    fi
    
    if ! curl -s http://localhost:8002/health > /dev/null; then
        echo "ERROR: Mock Image service not running on port 8002"
        all_running=false
    fi
    
    # Bot check is less reliable, so we'll just warn
    if ! curl -s http://localhost:8000/telegram -X POST -d '{}' -H "Content-Type: application/json" > /dev/null 2>&1; then
        echo "WARNING: Bot webhook might not be responding (this could be normal)"
    fi
    
    if [ "$all_running" = false ]; then
        echo ""
        echo "Please start the services first:"
        echo "  cd $SCRIPT_DIR"
        echo "  ./start_services.sh"
        exit 1
    fi
}

# Run a single stress test scenario
run_scenario() {
    local users=$1
    local spawn_rate=$2
    local duration=$3
    local name=$4
    
    echo ""
    echo "=== Running Scenario: $name ==="
    echo "Users: $users, Spawn Rate: $spawn_rate/sec, Duration: $duration"
    echo "Starting at: $(date)"
    
    # Create results directory
    local results_dir="$SCRIPT_DIR/results/$(date +%Y%m%d_%H%M%S)_${name}"
    mkdir -p "$results_dir"
    
    # Run locust test
    cd "$SCRIPT_DIR"
    
    locust \
        -f locustfile.py \
        --host=http://localhost:8000 \
        --users $users \
        --spawn-rate $spawn_rate \
        --run-time $duration \
        --headless \
        --html "$results_dir/report.html" \
        --csv "$results_dir/stats" \
        --logfile "$results_dir/locust.log" \
        --loglevel INFO
    
    echo "✓ Scenario completed. Results saved to: $results_dir"
    
    # Brief pause between scenarios
    echo "Waiting 10 seconds before next scenario..."
    sleep 10
}

# Main execution
main() {
    echo "Checking if services are running..."
    check_services
    echo "✓ All services are running"
    
    # Change to project directory and activate venv
    cd "$PROJECT_DIR"
    source venv/bin/activate
    
    # Check if locust is installed
    if ! command -v locust &> /dev/null; then
        echo "Installing locust..."
        pip install locust
    fi
    
    echo "Starting automated stress test sequence..."
    
    # Run the 5 scenarios with doubling user counts
    run_scenario 10 2 "30s" "01_baseline_10users"
    run_scenario 20 4 "30s" "02_double_20users" 
    run_scenario 40 8 "30s" "03_quad_40users"
    run_scenario 80 16 "30s" "04_oct_80users"
    run_scenario 160 32 "30s" "05_max_160users"
    
    echo ""
    echo "=== Stress Testing Complete! ==="
    echo "Results are saved in: $SCRIPT_DIR/results/"
    echo ""
    echo "To analyze results:"
    echo "  - Open the HTML reports in your browser"
    echo "  - Check CSV files for detailed statistics"
    echo "  - Review log files for any errors"
}

# Handle interruption
trap 'echo "Stress test interrupted by user"; exit 1' INT

# Run main function
main "$@"