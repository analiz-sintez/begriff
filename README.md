# Begriff: a Language Bot

A Telegram bot that helps you study foreign languages by combining the power of spaced repetition for building a strong vocabulary and language models to generate personalized learning content for you.

It knows your vocabulary, adapts to your level, and uses understandable language, gradually raising the bar.

<p float="left" align="middle">
<img src="https://github.com/user-attachments/assets/71493bc6-ae08-44ab-a432-d3f541c2dee9" width="24%" /> 
<img src="https://github.com/user-attachments/assets/f097fe7c-fc70-4cd3-9452-7a4213712c1e" width="24%" /> 
<img src="https://github.com/user-attachments/assets/7ab36e70-a1d6-4406-8618-792c9c16396b" width="24%" />  
<img src="https://github.com/user-attachments/assets/02b85988-377f-4ee0-9765-6eb108c78dfc" width="24%" />
</p>

## What You Can Do With It

- Get explanations for unfamiliar words you encounter while reading.
- Study those words so you don't forget them when you come across them again. Repeat only words you find difficult, and don’t waste time on known ones.
- If a word is tough to remember, get a helpful picture.
- Get help reading web pages you're interested in: paste a URL and receive a short recap using words you’re currently studying.
- Check a sentence for grammar and lexical correctness if you're in doubt.

## How to Try

1. Find the bot on Telegram: [BegriffBot](https://t.me/BegriffBot).
2. Say `/start`.
3. It will guide you through the process.

## Planned Features

- Cooperative mode: share words, explanations, recaps, etc., with your tutor or buddy.
- Word usage examples and other study materials.
- Voice samples to practice listening.

## How it Works

It uses an LLM to generate explanations and process text input, and an image generation neural network to produce pictures. If you host the bot yourself, you can configure it to use any OpenAI-compatible cloud or local LLM.

It schedules word repetitions via the FSRS algorithm — the same one used in Anki flashcards software.

## Setup

1. Clone this repository.
2. Run `make venv & make db-init` to create the virtual environment, install dependencies, and start the app.
3. Add a `.venv` file to the repo directory, and add `TELEGRAM_BOT_TOKEN=<your-token>` into it.
4. To start the HTTP API, run `make run`. The server will start on `localhost:5000`.
5. To start the Telegram bot backend, run `make tg`. It works via long-polling, so it doesn't require an external IP address.

## Makefile Usage

To streamline development tasks, this project utilizes a Makefile with the following commands:

- **`make venv`**: Creates or recreates the virtual environment and installs dependencies.
- **`make run`**: Activates the virtual environment and runs the Flask application in development mode.
- **`make tg`**: Activates the virtual environment and runs the Telegram bot backend.

For development:

- **`make migrate`**: Updates the database if changes were made.
- **`make test`**: Runs the test suite using pytest to ensure code functionality.
- **`make clean`**: Removes the virtual environment (useful for resetting dependencies).
