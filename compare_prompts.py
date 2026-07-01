#!/usr/bin/env python3
"""Automated comparison of prompt strategies and temperature settings.

Runs the same fixed quiz session (canned inputs) through each strategy ×
temperature combination, saves transcripts for side-by-side review.
"""

import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from main import QuizTutor
from prompts import PROMPT_STRATEGIES

CANNED_INPUTS = [
    "Python",
    "easy",
    "hint",
    "A",
    "hint",
    "B",
    "hint",
    "A",
    "hint",
    "B",
    "quit",
]


def run_scripted_session(strategy_name: str, temperature: float) -> str:
    """Run a scripted quiz session with the given strategy and temperature.
    Returns the captured output as a string."""
    strategy = PROMPT_STRATEGIES[strategy_name]
    tutor = QuizTutor(
        system_prompt=strategy["system_prompt"],
        hint_prompt=strategy["hint_prompt"],
        temperature=temperature,
    )
    buf = io.StringIO()
    with mock.patch("builtins.input", side_effect=CANNED_INPUTS), redirect_stdout(buf):
        try:
            tutor.start_new_quiz()
        except IndexError, StopIteration:
            # canned inputs exhausted before quiz ended — that's fine,
            # just means we got through most questions and/or hinted on all of them
            pass
    return buf.getvalue()


def main():
    """Run all 4 combinations and save transcripts."""
    comparisons_dir = Path("comparisons")
    comparisons_dir.mkdir(exist_ok=True)

    print("Running comparison of prompt strategies and temperatures...")
    print(f"Input sequence: {CANNED_INPUTS}\n")

    results = {}
    for strategy_name in sorted(PROMPT_STRATEGIES.keys()):
        for temperature in [0.2, 0.8]:
            print(
                f"Running {strategy_name} @ temp {temperature}...", end=" ", flush=True
            )
            transcript = run_scripted_session(strategy_name, temperature)
            filename = f"{strategy_name}_temp{temperature}.txt"
            filepath = comparisons_dir / filename
            filepath.write_text(transcript)
            results[(strategy_name, temperature)] = len(transcript)
            print(f"✓ ({len(transcript)} chars)")

    print("\n" + "=" * 70)
    print("TRANSCRIPTS SAVED")
    print("=" * 70)
    for (strategy, temp), size in sorted(results.items()):
        filepath = comparisons_dir / f"{strategy}_temp{temp}.txt"
        print(f"  {filepath}")
    print("\nCompare side-by-side with, e.g.:")
    print("  diff comparisons/encouraging_temp0.2.txt comparisons/concise_temp0.2.txt")
    print("  diff comparisons/concise_temp0.2.txt comparisons/concise_temp0.8.txt")


if __name__ == "__main__":
    main()
