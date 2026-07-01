from dataclasses import dataclass


@dataclass
class QuizResult:
    """Result of answering a single quiz question."""

    question_number: int
    topic: str
    question: str
    matched: bool
    correct: bool | None
    user_answer: str
    correct_text: str
    explanation: str = ""
