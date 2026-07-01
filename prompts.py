from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quiz_result import QuizResult

"""System prompts and prompt templates for Quiz Tutor application."""

CONCISE_SYSTEM_PROMPT = """You are a quiz tutor. Evaluate answers accurately and briefly.
State whether the answer is correct or incorrect, give a one-sentence reason, and move on.
No elaboration, no encouragement phrases, no padding.
Use only the real quiz questions, answers, and explanations provided — do not invent your own."""

QUIZ_TUTOR_SYSTEM_PROMPT = """You are an expert quiz tutor. Your responsibilities are:
1. Present quiz questions to users fairly
2. Evaluate user answers and provide constructive feedback
3. Help users learn by offering hints when they're struggling
4. Track the user's progress and provide performance summaries

When evaluating answers:
- Be encouraging but honest about correctness
- Provide detailed explanations for why an answer is correct or incorrect
- Suggest ways to remember or understand the concept better

Keep responses concise and conversational. After each answer evaluation, ask if the user wants to continue to the next question.

Use only the real quiz questions, answers, and explanations provided — do not invent your own."""


TOPIC_LIST_REQUEST_PROMPT = (
    "I'd like to start a new quiz. Please show me the list of available topics."
)


def get_list_quizzes_prompt(topic: str, difficulty: str) -> str:
    """Prompt for forced list_quizzes call — just enough context for Claude
    to fill in the category/difficulty parameters."""
    return f"The user wants a quiz on '{topic}' at {difficulty} difficulty."


SELECT_QUIZ_PROMPT = (
    "From the quizzes above, pick one (you choose which) and fetch its full details. "
    "Then begin by asking the user the first question. "
    "When presenting multiple-choice options, use the 'label' field from the tool data "
    "(e.g., label 'A' for the first option, 'B' for the second, etc.)."
)

CONCISE_HINT_PROMPT = "Give a one-sentence hint. No elaboration."

HINT_REQUEST_PROMPT = (
    "Can you provide a helpful hint for this question without giving away the answer?"
)

NEXT_QUESTION_PROMPT = "Move to the next question, please."

QUIZ_SUMMARY_PROMPT = (
    "Please provide a brief summary of my performance on this quiz, "
    "including strengths and areas for improvement."
)


def get_quiz_summary_prompt(results: list[QuizResult]) -> str:
    """
    Build an enriched summary prompt using actual per-question results (QuizResult instances).
    Falls back to QUIZ_SUMMARY_PROMPT if results is empty.
    """
    if not results:
        return QUIZ_SUMMARY_PROMPT

    summary_lines = [
        "Based on my performance on this quiz, here are the actual results:\n"
    ]

    correct_count = sum(1 for r in results if r.correct is True and r.matched)
    total_graded = sum(1 for r in results if r.matched)
    unknown_count = sum(1 for r in results if not r.matched)

    summary_lines.append(f"Topic: {results[0].topic}\n")
    summary_lines.append(f"Answered: {len(results)} questions\n")
    summary_lines.append(
        f"Correct: {correct_count} out of {total_graded} graded questions\n"
    )
    if unknown_count > 0:
        summary_lines.append(f"Unable to verify: {unknown_count} answer(s)\n")
    summary_lines.append("\nDetailed breakdown:\n")

    for result in results:
        if not result.matched:
            status = "❓ (unverified answer)"
        elif result.correct:
            status = "✓ (correct)"
        else:
            status = "✗ (incorrect)"

        summary_lines.append(
            f"{result.question_number}. {result.question}\n"
            f"   Your answer: {result.user_answer}\n"
            f"   Correct answer: {result.correct_text}\n"
            f"   Result: {status}\n"
        )

    summary_lines.append(
        "\nPlease provide a brief summary of my performance, "
        "highlighting what I got right, what I got wrong, and areas for improvement."
    )

    return "".join(summary_lines)


def get_prompt_strategies():
    """Return available prompt strategies as a dict."""
    return {
        "encouraging": {
            "system_prompt": QUIZ_TUTOR_SYSTEM_PROMPT,
            "hint_prompt": HINT_REQUEST_PROMPT,
        },
        "concise": {
            "system_prompt": CONCISE_SYSTEM_PROMPT,
            "hint_prompt": CONCISE_HINT_PROMPT,
        },
    }


PROMPT_STRATEGIES = get_prompt_strategies()
