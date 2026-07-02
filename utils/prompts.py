from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.quiz_result import QuizResult

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


def get_question_feedback_prompt(result: QuizResult) -> str:
    """
    Build an isolated, single-question feedback prompt for a wrong/unmatched answer.
    Contains only that question's ground truth — question text, user's answer,
    correct answer, and explanation (if present). No mention of other questions.
    Instructs Claude to explain in 2-3 sentences why the answer was wrong and
    what to remember, using only the given information — never invent.
    """
    explanation_line = (
        f"Explanation from the quiz: {result.explanation}\n"
        if result.explanation
        else ""
    )

    if result.matched:
        return (
            f"A quiz taker answered this question incorrectly:\n\n"
            f"Question: {result.question}\n"
            f"Their answer: {result.user_answer}\n"
            f"Correct answer: {result.correct_text}\n"
            f"{explanation_line}\n"
            "In 2-3 sentences, explain why their answer was wrong and what "
            "concept or fact to remember for next time. Use only the information "
            "given above — do not invent details about this question."
        )
    else:
        return (
            f"A quiz taker provided an answer that could not be matched to any "
            f"of the available options:\n\n"
            f"Question: {result.question}\n"
            f"Their answer: {result.user_answer}\n"
            f"Correct answer: {result.correct_text}\n"
            f"{explanation_line}\n"
            "In 2-3 sentences, explain what the correct answer is and why their "
            "response did not match the available options. Use only the information "
            "given above — do not invent details about this question."
        )


def get_areas_of_improvement_prompt(
    wrong_results: list[QuizResult], feedback_by_question: dict[int, str]
) -> str:
    """
    Build a synthesis prompt for identifying general areas of improvement
    from the aggregated wrong/unmatched answers and their generated feedback.
    Takes only incorrect results and their feedback (not the full transcript).
    Asks for a short general paragraph identifying patterns/themes, not per-question restatement.
    """
    feedback_block = "\n".join(
        f"Q{r.question_number}: {feedback_by_question.get(r.question_number, '(no feedback generated)')}"
        for r in wrong_results
    )

    return (
        f"Based on these {len(wrong_results)} incorrect answers and their feedback:\n\n"
        f"{feedback_block}\n\n"
        "Provide a short paragraph (3-4 sentences) identifying general themes or "
        "areas of improvement. Do not restate individual question details — focus on "
        "overarching concepts or knowledge gaps. Use only the feedback above."
    )


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
