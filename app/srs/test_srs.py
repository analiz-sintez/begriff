import os
import pytest
import time
import random
import math
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from nachricht import create_app, db
from nachricht.auth import User

from app.config import Config as DefaultConfig
from app.notes import Language
from app.srs import (
    create_word_note,
    get_cards,
    count_new_cards_studied,
    record_view_start,
    record_answer,
    Answer,
    Maturity,
)


basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


class Config(DefaultConfig):
    TESTING = True
    # SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(
        basedir, "data/database.test-srs.sqlite"
    )


@pytest.fixture
def app():
    """Provides a clean application and database context for the test."""
    app = create_app(Config)
    with app.app_context():
        db.drop_all()
        db.create_all()
        language = Language(name="Klingon")
        user = User(login="stress_tester")
        db.session.add(language)
        db.session.add(user)
        db.session.commit()
    yield app


def _generate_data(user: User, language: Language, num_notes: int):
    """Generates test data: notes, cards, and a simulated study history."""
    notes = []
    for i in range(num_notes):
        note = create_word_note(
            f"word_{user.id}_{i}", f"explanation_{i}", language.id, user.id
        )
        notes.append(note)

    all_cards = [card for note in notes for card in note.cards]
    random.shuffle(all_cards)

    for card in all_cards:
        num_reviews = random.randint(0, 15)
        if not num_reviews:
            continue

        # Start reviews from a random point in the past.
        review_time = datetime.now(timezone.utc) - timedelta(
            days=random.randint(60, 365)
        )

        for i in range(num_reviews):
            if i > 0:
                # Advance time based on card's last known stability.
                interval = int(card.stability or 1)
                review_time += timedelta(days=random.randint(1, interval + 5))

            with patch("app.srs.view.now") as mock_now:
                mock_now.return_value = review_time
                view_id = record_view_start(card.id)
                answer = random.choice(list(Answer))
                record_answer(view_id, answer)


def _run_benchmark(func: callable, repetitions: int = 10) -> tuple:
    """Runs a function multiple times and returns timing statistics."""
    times = []
    for _ in range(repetitions):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append(end - start)

    mean = sum(times) / repetitions
    if repetitions > 1:
        variance = sum((x - mean) ** 2 for x in times) / (repetitions - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0

    # 95% confidence interval.
    z_score = 1.96
    ci_margin = z_score * (std_dev / math.sqrt(repetitions))
    ci = (mean - ci_margin, mean + ci_margin)

    return mean, std_dev, ci


def test_get_cards_performance(app):
    """
    Measures the performance of the `get_cards` function with varying
    data sizes and filter configurations.
    """
    print("\n\n--- `get_cards` Performance Test ---")
    repetitions = 10

    param_sets = {
        "count_new_cards_studied": {
            "baseline": {},
        },
        "get_cards": {
            "baseline": {},
            "with_end_ts": {
                "end_ts": datetime.now(timezone.utc) + timedelta(days=30)
            },
            "bury_siblings": {
                "end_ts": datetime.now(timezone.utc) + timedelta(days=30),
                "bury_siblings": True,
            },
            "maturity_new": {"maturity": [Maturity.NEW]},
            "maturity_young": {"maturity": [Maturity.YOUNG]},
            "maturity_all": {
                "maturity": [Maturity.NEW, Maturity.YOUNG, Maturity.MATURE]
            },
            "randomized": {"randomize": True},
        },
        "get_remaining_cards": {},
    }

    results = {}

    note_counts = [5, 50]

    for num_notes in note_counts:
        with app.app_context():
            db.drop_all()
            db.create_all()
            user = User(login=f"tester_{num_notes}")
            language = Language(name="Klingon")
            db.session.add(user)
            db.session.add(language)
            db.session.commit()

            print(f"\nGenerating data for {num_notes} notes...")
            _generate_data(user, language, num_notes)

            results[num_notes] = {}
            print(
                f"Benchmarking with {num_notes} notes ({num_notes*2} cards)..."
            )

            for func_name, func_param_sets in param_sets.items():
                for test_name, params in func_param_sets.items():
                    if func_name == "get_cards":
                        benchmark_func = lambda: get_cards(
                            user_id=user.id, language=language, **params
                        )
                    elif func_name == "count_new_cards_studied":
                        benchmark_func = lambda: count_new_cards_studied(
                            user, language, **params
                        )
                    else:
                        continue

                    mean, std_dev, ci = _run_benchmark(
                        benchmark_func, repetitions
                    )
                    results[num_notes][func_name] = (mean, std_dev, ci)

                    # Print results immediately after the test for the current num_notes
                    print(
                        f"{func_name:10.10}: "
                        f"{test_name:15.15}: "
                        f"Avg: {mean:.4f}s | "
                        f"StdDev: {std_dev:.4f}s | "
                        f"95% CI: [{ci[0]:.4f}, {ci[1]:.4f}]s"
                    )

    print("\n--- Test Complete ---")
