VENV_PATH := venv
PYTHON_BIN := python3

.PHONY: all venv run clean db-init migrate

all: venv db-init run

# Create or recreate virtual environment and install dependencies
venv: 
	@if [ ! -d "$(VENV_PATH)" ]; then \
		$(PYTHON_BIN) -m venv $(VENV_PATH); \
	fi
	. $(VENV_PATH)/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

poetry:
	cat ./requirements.txt | grep -v "@" | xargs poetry add

# Run the web application in development mode
web: 
	. $(VENV_PATH)/bin/activate && FLASK_APP=run.py FLASK_ENV=development flask run --debug

# Run the Telegram bot pooling for testing purposes
tg: 
	. $(VENV_PATH)/bin/activate && python bin/autoreload_telegram.py

# Run background jobs
jobs:
	. $(VENV_PATH)/bin/activate && python bin/generate_note_images.py

# Run unit-tests
test:
	. $(VENV_PATH)/bin/activate && pytest

test-verbose:
	. $(VENV_PATH)/bin/activate && pytest -s --log-cli-level=INFO

# Run static type analyzer
types:
	. $(VENV_PATH)/bin/activate && pyright app

# Initialize the database
db-init:
	. $(VENV_PATH)/bin/activate && flask db init

# Update database migrations
migrate:
	. $(VENV_PATH)/bin/activate && flask db migrate && flask db upgrade

# Clean the virtual environment and remove the existing database
clean:
	rm -rf $(VENV_PATH)
	rm -f data/database.sqlite
