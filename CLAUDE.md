# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Begriff is a Telegram bot that helps users study foreign languages through spaced repetition and AI-generated content. It combines vocabulary building with personalized learning materials, adapting to the user's level and gradually increasing difficulty.

## Architecture

The codebase follows a modular Flask application structure:

- **app/**: Core application modules
  - **srs/**: Spaced Repetition System (SRS) using FSRS algorithm for card scheduling
  - **telegram/**: Telegram bot handlers and flows (onboarding, study, note management, etc.)
  - **llm/**: Language model integration (OpenAI/Ollama) for content generation
  - **image/**: Image generation service using Vertex AI
  - **notes/**: Note management system with polymorphic models
  - **config.py**: Central configuration with LLM, Telegram, and feature settings

- **migrations/**: Database migrations using Flask-Migrate/Alembic
- **docs/**: Sequence diagrams and architectural documentation
- **tests/**: Test suite covering API, models, services, and Telegram functionality

The application uses the `nachricht` framework (custom messaging framework) for handling Telegram interactions through routers and signal buses.

## Development Commands

### Environment Setup
```bash
make venv          # Create virtual environment and install dependencies
make db-init       # Initialize database
```

### Running the Application
```bash
make tg            # Run Telegram bot (long-polling)
make jobs          # Run background jobs (image generation)
```

### Development Tools
```bash
make test          # Run test suite with pytest
make test-verbose  # Run tests with verbose output and logging
make types         # Run static type checking with pyright
```

### Database Management
```bash
make db-migrate m="description"  # Create migration
make db-upgrade    # Apply migrations (backs up database first)
```

### Dependencies
```bash
make nachricht     # Force-reinstall nachricht framework
make clean         # Remove virtual environment
```

## Configuration

The bot requires a `.venv` file in the root directory with:
```
TELEGRAM_BOT_TOKEN=<your-token>
OPENAI_API_KEY=<your-key>  # For LLM features
```

Key configuration sections in `app/config.py`:
- **LLM**: Model selection, API endpoints (OpenAI/Ollama)
- **IMAGE**: Vertex AI image generation settings
- **FSRS**: Spaced repetition parameters
- **LANGUAGE**: Supported study languages and defaults
- **UX**: User experience toggles

## Key Components

### SRS System
Uses FSRS algorithm for optimal card scheduling. Cards have different types (explanation, image, translation) and track difficulty, retention, and review history.

### Language Detection & Processing
Supports 20+ languages with automatic language detection, morphological analysis (pymorphy3), and base form conversion.

### Telegram Bot Flow
Complex conversation flows handled through the nachricht framework:
- Onboarding with language selection
- Study sessions with card reviews
- Note creation from explanations
- URL recap generation
- Image generation for difficult words

### Database Schema
SQLAlchemy models with polymorphic inheritance for notes and cards. Uses UTC timestamps and proper foreign key relationships.

## Testing

Run `make test` for the full test suite. Tests cover:
- API endpoints
- Database models and migrations
- Telegram bot interactions
- LLM service integration
- Image generation service

Individual test files can be run with: `pytest tests/test_<module>.py`

## Development Notes

- The application requires Python 3.13+
- Uses Flask with async support for handling concurrent requests
- Database migrations are automatically backed up before upgrades
- The nachricht framework handles Telegram bot complexity through routers and signal buses
- Image generation is handled as background jobs to avoid blocking user interactions