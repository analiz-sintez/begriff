# Begriff: a Language Bot

![Begriff Bot](./begriff.jpg)

A telegram bot helps you to study language, combining power of spaced repetition for building firm vocabulary and LLM for generating content and for practice.

Since it knows your vocabulary, it adopts to your level and speaks understandable language, gradually rising the bar.

## How to Try

1. Find the bot on Telegram: [BegriffBot](t.me/BegriffBot).
2. Say `/hello`.
3. It will tell you what to do.

## Limitations and Plans

- only English (planning to support all major languages)
- doesn't adopt to your level (will know your vocabulary and use it for explanations and chats)
- doesn't chat (coming soon)
- doesn't have voice (coming soon)

## Setup

1. Clone this repository.
2. Run `make venv & make db-init` to create venv, install dependencies and start the app.
3. Add `.venv` file into the repo dir, add `TELEGRAM_BOT_TOKEN=<your-token>` into it.
4. To start HTTP API run `make run`, the server will start on `localhost:5000`.
5. To start Telegram bot backend run `make tg`. It works via long-polling so it doesn't require external IP address.

## Usage

- Access API docs at `/apidocs` after running the web server.
- Send reports via Telegram bot in the following format: `[[<Project>/]<Task>/]<Work description>: <hours spent> [(<comment>)]` (optional things are in square brackets, e.g. "Very important work: 4.5" is fine).

## Makefile Usage

To streamline development tasks, this project utilizes a Makefile with the following commands:

- **`make venv`**: Creates or recreates the virtual environment and installs dependencies.
- **`make run`**: Activates the virtual environment and runs the Flask application in development mode.
- **`make tg`**: Activates the virtual environment and runs telegram bot backend.

For development:

- **`make migrate`**: Updates the database if it was changed.
- **`make test`**: Runs the test suite using pytest to ensure code functionality.
- **`make clean`**: Removes the virtual environment (useful for resetting dependencies).
