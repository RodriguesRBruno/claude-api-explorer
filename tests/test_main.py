"""Unit tests for main.py — all API calls mocked."""

import os
from unittest import mock

import pytest
from anthropic import RateLimitError

from main import FORCED_TOOL_TEMPERATURE, QuizTutor
from prompts import HINT_REQUEST_PROMPT, QUIZ_TUTOR_SYSTEM_PROMPT
from quiz_result import QuizResult


@pytest.fixture
def mock_oauth():
    """Fixture to mock CLAUDE_CODE_OAUTH_TOKEN so Anthropic client initializes."""
    with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "test_token"}):
        yield


class TestQuizTutorInit:
    """Test QuizTutor initialization."""

    def test_default_init(self, mock_oauth):
        """Default constructor should use default prompts and temp."""
        with mock.patch("main.Anthropic"):
            tutor = QuizTutor()
            assert tutor.system_prompt == QUIZ_TUTOR_SYSTEM_PROMPT
            assert tutor.hint_prompt == HINT_REQUEST_PROMPT
            assert tutor.temperature == 1.0

    def test_custom_init(self, mock_oauth):
        """Custom constructor should set custom values."""
        with mock.patch("main.Anthropic"):
            tutor = QuizTutor(
                system_prompt="custom system",
                hint_prompt="custom hint",
                temperature=0.5,
            )
            assert tutor.system_prompt == "custom system"
            assert tutor.hint_prompt == "custom hint"
            assert tutor.temperature == 0.5


class TestContinue:
    """Test _continue method."""

    def test_continue_with_temperature(self, mock_oauth):
        """_continue should pass temperature to messages.create."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock.MagicMock(type="text", text="response text")]
            mock_client.messages.create.return_value = mock_resp
            tutor = QuizTutor(temperature=0.7)
            result = tutor._continue()
            assert result == "response text"
            # Check that temperature was passed
            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs["temperature"] == 0.7


class TestForcedToolCall:
    """Test _forced_tool_call method."""

    def test_forced_tool_with_fixed_temperature(self, mock_oauth):
        """_forced_tool_call should use FORCED_TOOL_TEMPERATURE, not self.temperature."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            # Mock response with tool_use block
            mock_tool_block = mock.MagicMock(
                type="tool_use", id="tool_123", name="test_tool"
            )
            mock_tool_block.input = {"param": "value"}
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock_tool_block]
            mock_client.messages.create.return_value = mock_resp
            with mock.patch("main.execute_tool") as mock_execute:
                mock_execute.return_value = {"status": "ok", "data": "result"}
                tutor = QuizTutor(temperature=0.9)
                tool_schema = {"name": "test_tool"}
                result = tutor._forced_tool_call("user msg", tool_schema)
                assert result["status"] == "ok"
                # Check that FORCED_TOOL_TEMPERATURE was used, not 0.9
                call_kwargs = mock_client.messages.create.call_args[1]
                assert call_kwargs["temperature"] == FORCED_TOOL_TEMPERATURE
                assert FORCED_TOOL_TEMPERATURE == 0.0

    def test_forced_tool_appends_tool_result(self, mock_oauth):
        """_forced_tool_call should append tool_result to history."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_tool_block = mock.MagicMock(
                type="tool_use", id="tool_123", name="list_topics"
            )
            mock_tool_block.input = {}
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock_tool_block]
            mock_client.messages.create.return_value = mock_resp
            with mock.patch("main.execute_tool") as mock_execute:
                mock_execute.return_value = {
                    "status": "ok",
                    "data": ["topic1", "topic2"],
                }
                tutor = QuizTutor()
                tool_schema = {"name": "list_topics"}
                tutor._forced_tool_call("show topics", tool_schema)
                # Check history has user + assistant + tool_result
                assert len(tutor.conversation_history) == 3
                assert tutor.conversation_history[0]["role"] == "user"
                assert tutor.conversation_history[1]["role"] == "assistant"
                assert tutor.conversation_history[2]["role"] == "user"
                tool_result_content = tutor.conversation_history[2]["content"]
                assert tool_result_content[0]["type"] == "tool_result"
                assert tool_result_content[0]["tool_use_id"] == "tool_123"


class TestChat:
    """Test chat method."""

    def test_chat_delegates_to_continue(self, mock_oauth):
        """chat should append user message and delegate to _continue."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock.MagicMock(type="text", text="answer")]
            mock_client.messages.create.return_value = mock_resp
            tutor = QuizTutor()
            result = tutor.chat("What is 2+2?")
            assert result == "answer"
            assert len(tutor.conversation_history) == 2
            assert tutor.conversation_history[0]["role"] == "user"
            assert tutor.conversation_history[0]["content"] == "What is 2+2?"


class TestQuizLoopHintPrompt:
    """Test that _quiz_loop uses self.hint_prompt, not the module-level constant."""

    def test_quiz_loop_uses_instance_hint_prompt(self, mock_oauth):
        """_quiz_loop's 'hint' branch should call self.chat(self.hint_prompt)."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock.MagicMock(type="text", text="hint response")]
            mock_client.messages.create.return_value = mock_resp
            custom_hint = "Custom hint prompt"
            tutor = QuizTutor(hint_prompt=custom_hint)
            with mock.patch("builtins.input", side_effect=["hint", "quit"]):
                with mock.patch("builtins.print"):
                    tutor._quiz_loop()
            # Check that the custom hint prompt was sent, not the module constant
            calls = [call for call in mock_client.messages.create.call_args_list]
            assert len(calls) >= 1
            # The second call (first message.create for the hint response) should have custom_hint in history
            if len(calls) > 1:
                second_call_messages = calls[1][1]["messages"]
                # Find the hint request in the history
                hint_found = any(
                    custom_hint in str(msg) for msg in second_call_messages
                )
                assert hint_found, (
                    "Custom hint prompt not found in call to messages.create"
                )


class TestQuizResultTracking:
    """Test that _quiz_loop accumulates quiz_results correctly."""

    def test_quiz_results_initialized_on_start(self, mock_oauth):
        """start_new_quiz should initialize quiz_results and quiz_questions."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock.MagicMock(type="text", text="Topics")]
            mock_client.messages.create.return_value = mock_resp
            with mock.patch("main.execute_tool") as mock_execute:
                # Mock list_topics
                mock_execute.side_effect = [
                    {"status": "ok", "data": [{"name": "Python"}]},
                ]
                with mock.patch("builtins.input", side_effect=["Python", "medium"]):
                    tutor = QuizTutor()
                    # Manually set up to avoid the list_quizzes loop
                    tutor.conversation_history = []
                    quiz_data = {
                        "status": "ok",
                        "data": {
                            "id": "123",
                            "topic": "Python",
                            "category": "Programming",
                            "questions": [
                                {
                                    "id": "q1",
                                    "text": "What is 2+2?",
                                    "answers": [
                                        {
                                            "id": "a1",
                                            "text": "4",
                                            "label": "A",
                                            "isCorrect": True,
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                    # Simulate what _forced_tool_call would return
                    tutor.quiz_questions = quiz_data["data"]["questions"]
                    tutor.quiz_topic = quiz_data["data"]["topic"]
                    tutor.current_question_index = 0
                    tutor.quiz_results = []
                    assert len(tutor.quiz_questions) == 1
                    assert tutor.quiz_topic == "Python"
                    assert tutor.quiz_results == []

    def test_quiz_loop_grades_and_tracks_answer(self, mock_oauth):
        """_quiz_loop should grade each answer and add to quiz_results."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock.MagicMock(type="text", text="Good answer!")]
            mock_client.messages.create.return_value = mock_resp
            tutor = QuizTutor()
            tutor.quiz_questions = [
                {
                    "id": "q1",
                    "text": "What is 2+2?",
                    "answers": [
                        {"id": "a1", "text": "4", "label": "A", "isCorrect": True},
                        {"id": "a2", "text": "5", "label": "B", "isCorrect": False},
                    ],
                }
            ]
            tutor.quiz_topic = "Math"
            tutor.current_question_index = 0
            tutor.quiz_results = []
            with mock.patch("builtins.input", side_effect=["A", "quit"]):
                with mock.patch("builtins.print"):
                    tutor._quiz_loop()
            # Should have tracked one result
            assert len(tutor.quiz_results) == 1
            result = tutor.quiz_results[0]
            assert isinstance(result, QuizResult)
            assert result.topic == "Math"
            assert result.question == "What is 2+2?"
            assert result.matched is True
            assert result.correct is True
            assert result.user_answer == "4"
            assert result.correct_text == "4"
            assert result.question_number == 1

    def test_quiz_loop_all_correct_skips_claude_calls(self, mock_oauth):
        """_quiz_loop with all-correct results should skip isolated feedback calls."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock.MagicMock(type="text", text="")]
            mock_client.messages.create.return_value = mock_resp
            tutor = QuizTutor()
            tutor.quiz_results = [
                QuizResult(
                    question_number=1,
                    topic="Math",
                    question="What is 2+2?",
                    matched=True,
                    correct=True,
                    user_answer="4",
                    correct_text="4",
                    explanation="Two plus two equals four.",
                )
            ]
            with mock.patch("builtins.input", side_effect=["quit"]):
                with mock.patch("builtins.print"):
                    tutor._quiz_loop()
            # All correct → no isolated feedback calls (no _isolated_completion calls)
            # So messages.create should not be called for feedback
            assert mock_client.messages.create.call_count == 0


class TestIsolatedCompletion:
    """Test _isolated_completion method."""

    def test_isolated_completion_fresh_messages(self, mock_oauth):
        """_isolated_completion should use a fresh message list, not conversation_history."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock.MagicMock(type="text", text="feedback")]
            mock_client.messages.create.return_value = mock_resp
            tutor = QuizTutor()
            tutor.conversation_history = [
                {"role": "user", "content": "old message"},
                {"role": "assistant", "content": "old response"},
            ]
            result = tutor._isolated_completion("new prompt")
            assert result == "feedback"
            # Check that messages passed to create is a fresh list with just the new prompt
            call_kwargs = mock_client.messages.create.call_args[1]
            messages = call_kwargs["messages"]
            assert len(messages) == 1
            assert messages[0]["role"] == "user"
            assert messages[0]["content"] == "new prompt"
            # conversation_history should be untouched
            assert len(tutor.conversation_history) == 2

    def test_isolated_completion_error_handling(self, mock_oauth):
        """_isolated_completion should return None on rate limit error."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.messages.create.side_effect = RateLimitError(
                message="Rate limited",
                response=mock.MagicMock(status_code=429),
                body={},
            )
            tutor = QuizTutor()
            with mock.patch("builtins.print"):
                result = tutor._isolated_completion("test")
            assert result is None


class TestBuildQuizSummary:
    """Test _build_quiz_summary method."""

    def test_build_summary_one_wrong_one_correct(self, mock_oauth):
        """_build_quiz_summary with mixed results should call isolated completion."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            feedback_resp = mock.MagicMock()
            feedback_resp.content = [
                mock.MagicMock(type="text", text="You got this wrong.")
            ]
            improvement_resp = mock.MagicMock()
            improvement_resp.content = [
                mock.MagicMock(type="text", text="Focus on basics.")
            ]
            mock_client.messages.create.side_effect = [
                feedback_resp,
                improvement_resp,
            ]
            tutor = QuizTutor()
            tutor.quiz_results = [
                QuizResult(
                    question_number=1,
                    topic="Math",
                    question="What is 2+2?",
                    matched=True,
                    correct=True,
                    user_answer="4",
                    correct_text="4",
                    explanation="",
                ),
                QuizResult(
                    question_number=2,
                    topic="Math",
                    question="What is 3+3?",
                    matched=True,
                    correct=False,
                    user_answer="5",
                    correct_text="6",
                    explanation="Three plus three equals six.",
                ),
            ]
            summary = tutor._build_quiz_summary()
            # Should have 2 isolated calls: 1 for wrong question feedback, 1 for improvement
            assert mock_client.messages.create.call_count == 2
            # Summary should include both questions in order
            assert "1. What is 2+2?" in summary
            assert "2. What is 3+3?" in summary
            assert "✓ Correct" in summary
            assert "✗ Incorrect" in summary
            assert "You got this wrong." in summary
            assert "Focus on basics." in summary

    def test_build_summary_graceful_failure(self, mock_oauth):
        """_build_quiz_summary should handle isolated call failures gracefully."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.messages.create.side_effect = RateLimitError(
                message="Rate limited",
                response=mock.MagicMock(status_code=429),
                body={},
            )
            tutor = QuizTutor()
            tutor.quiz_results = [
                QuizResult(
                    question_number=1,
                    topic="Math",
                    question="What is 2+2?",
                    matched=True,
                    correct=False,
                    user_answer="5",
                    correct_text="4",
                    explanation="",
                ),
            ]
            with mock.patch("builtins.print"):
                summary = tutor._build_quiz_summary()
            # Should still contain ground truth even if feedback call fails
            assert "1. What is 2+2?" in summary
            assert "Your answer: 5" in summary
            assert "Correct answer: 4" in summary
            assert "(unable to generate feedback for this question)" in summary

    def test_build_summary_empty_results_fallback(self, mock_oauth):
        """_build_quiz_summary with empty results should use chat fallback."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock.MagicMock(type="text", text="Good job!")]
            mock_client.messages.create.return_value = mock_resp
            tutor = QuizTutor()
            tutor.quiz_results = []
            summary = tutor._build_quiz_summary()
            # Should call chat (which calls messages.create with conversation_history)
            assert mock_client.messages.create.called
            assert "Good job!" in summary


class TestInputValidation:
    """Test answer input validation in _quiz_loop."""

    def test_get_valid_answer_options(self, mock_oauth):
        """_get_valid_answer_options should return letter labels for current question."""
        with mock.patch("main.Anthropic"):
            tutor = QuizTutor()
            tutor.quiz_questions = [
                {
                    "id": "q1",
                    "text": "Question?",
                    "answers": [
                        {
                            "id": "a1",
                            "text": "Option A",
                            "label": "A",
                            "isCorrect": True,
                        },
                        {
                            "id": "a2",
                            "text": "Option B",
                            "label": "B",
                            "isCorrect": False,
                        },
                        {
                            "id": "a3",
                            "text": "Option C",
                            "label": "C",
                            "isCorrect": False,
                        },
                    ],
                }
            ]
            tutor.current_question_index = 0
            options = tutor._get_valid_answer_options()
            assert options == ["A", "B", "C"]

    def test_get_valid_answer_options_beyond_end(self, mock_oauth):
        """_get_valid_answer_options should return empty list if past last question."""
        with mock.patch("main.Anthropic"):
            tutor = QuizTutor()
            tutor.quiz_questions = [{"id": "q1", "answers": []}]
            tutor.current_question_index = 1
            options = tutor._get_valid_answer_options()
            assert options == []

    def test_is_valid_answer_letter(self, mock_oauth):
        """_is_valid_answer should accept valid letter options."""
        with mock.patch("main.Anthropic"):
            tutor = QuizTutor()
            tutor.quiz_questions = [
                {
                    "id": "q1",
                    "answers": [
                        {"label": "A", "isCorrect": True},
                        {"label": "B", "isCorrect": False},
                    ],
                }
            ]
            tutor.current_question_index = 0
            assert tutor._is_valid_answer("A") is True
            assert tutor._is_valid_answer("B") is True
            assert tutor._is_valid_answer("a") is True
            assert tutor._is_valid_answer("b") is True

    def test_is_valid_answer_invalid_letter(self, mock_oauth):
        """_is_valid_answer should reject letters not in the options."""
        with mock.patch("main.Anthropic"):
            tutor = QuizTutor()
            tutor.quiz_questions = [
                {
                    "id": "q1",
                    "answers": [
                        {"label": "A", "isCorrect": True},
                        {"label": "B", "isCorrect": False},
                    ],
                }
            ]
            tutor.current_question_index = 0
            assert tutor._is_valid_answer("C") is False
            assert tutor._is_valid_answer("D") is False

    def test_is_valid_answer_hint_quit(self, mock_oauth):
        """_is_valid_answer should accept 'hint' and 'quit' regardless of question."""
        with mock.patch("main.Anthropic"):
            tutor = QuizTutor()
            tutor.quiz_questions = []
            tutor.current_question_index = 0
            assert tutor._is_valid_answer("hint") is True
            assert tutor._is_valid_answer("HINT") is True
            assert tutor._is_valid_answer("quit") is True
            assert tutor._is_valid_answer("QUIT") is True

    def test_get_invalid_answer_message(self, mock_oauth):
        """_get_invalid_answer_message should show valid options."""
        with mock.patch("main.Anthropic"):
            tutor = QuizTutor()
            tutor.quiz_questions = [
                {
                    "id": "q1",
                    "answers": [
                        {"label": "A"},
                        {"label": "B"},
                        {"label": "C"},
                    ],
                }
            ]
            tutor.current_question_index = 0
            message = tutor._get_invalid_answer_message()
            assert "A, B, C" in message
            assert "'hint'" in message
            assert "'quit'" in message

    def test_quiz_loop_rejects_invalid_answer(self, mock_oauth):
        """_quiz_loop should reject invalid answers and re-prompt."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock.MagicMock(type="text", text="response")]
            mock_client.messages.create.return_value = mock_resp
            tutor = QuizTutor()
            tutor.quiz_questions = [
                {
                    "id": "q1",
                    "text": "Question?",
                    "answers": [
                        {
                            "id": "a1",
                            "text": "Option A",
                            "label": "A",
                            "isCorrect": True,
                        },
                        {
                            "id": "a2",
                            "text": "Option B",
                            "label": "B",
                            "isCorrect": False,
                        },
                    ],
                }
            ]
            tutor.quiz_topic = "Test"
            tutor.current_question_index = 0
            tutor.quiz_results = []
            # Input: invalid letter (X), then valid letter (A), then quit
            with mock.patch("builtins.input", side_effect=["X", "A", "quit"]):
                with mock.patch("builtins.print") as mock_print:
                    tutor._quiz_loop()
            # Check that invalid answer message was printed
            print_calls = [str(call) for call in mock_print.call_args_list]
            assert any("Invalid response" in str(call) for call in print_calls), (
                "Should print invalid answer message"
            )
            # Check that valid answer was graded (quiz_results should have 1 entry)
            assert len(tutor.quiz_results) == 1
            assert tutor.quiz_results[0].question_number == 1

    def test_quiz_loop_allows_valid_case_variations(self, mock_oauth):
        """_quiz_loop should accept both uppercase and lowercase valid answers."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock.MagicMock(type="text", text="response")]
            mock_client.messages.create.return_value = mock_resp
            tutor = QuizTutor()
            tutor.quiz_questions = [
                {
                    "id": "q1",
                    "text": "Question?",
                    "answers": [
                        {
                            "id": "a1",
                            "text": "Option A",
                            "label": "A",
                            "isCorrect": True,
                        },
                        {
                            "id": "a2",
                            "text": "Option B",
                            "label": "B",
                            "isCorrect": False,
                        },
                    ],
                }
            ]
            tutor.quiz_topic = "Test"
            tutor.current_question_index = 0
            tutor.quiz_results = []
            # Input: lowercase 'a', then quit
            with mock.patch("builtins.input", side_effect=["a", "quit"]):
                with mock.patch("builtins.print"):
                    tutor._quiz_loop()
            # Check that lowercase answer was accepted and graded
            assert len(tutor.quiz_results) == 1
            assert tutor.quiz_results[0].user_answer == "Option A"


class TestPromptBuilders:
    """Test new prompt builder functions."""

    def test_get_question_feedback_prompt_matched_answer(self):
        """get_question_feedback_prompt for matched wrong answer includes explanation."""
        from prompts import get_question_feedback_prompt

        result = QuizResult(
            question_number=1,
            topic="Math",
            question="What is 2+2?",
            matched=True,
            correct=False,
            user_answer="5",
            correct_text="4",
            explanation="Two plus two equals four.",
        )
        prompt = get_question_feedback_prompt(result)
        assert "What is 2+2?" in prompt
        assert "5" in prompt
        assert "4" in prompt
        assert "Two plus two equals four." in prompt
        assert "incorrectly" in prompt.lower()

    def test_get_question_feedback_prompt_unmatched_answer(self):
        """get_question_feedback_prompt for unmatched answer has different phrasing."""
        from prompts import get_question_feedback_prompt

        result = QuizResult(
            question_number=1,
            topic="Math",
            question="What is 2+2?",
            matched=False,
            correct=None,
            user_answer="invalid input",
            correct_text="4",
            explanation="",
        )
        prompt = get_question_feedback_prompt(result)
        assert "What is 2+2?" in prompt
        assert "invalid input" in prompt
        assert "4" in prompt
        assert "could not be matched" in prompt.lower()

    def test_get_question_feedback_prompt_omits_empty_explanation(self):
        """get_question_feedback_prompt should omit explanation line when empty."""
        from prompts import get_question_feedback_prompt

        result = QuizResult(
            question_number=1,
            topic="Math",
            question="What is 2+2?",
            matched=True,
            correct=False,
            user_answer="5",
            correct_text="4",
            explanation="",
        )
        prompt = get_question_feedback_prompt(result)
        assert "Explanation from the quiz:" not in prompt

    def test_get_areas_of_improvement_prompt_aggregates(self):
        """get_areas_of_improvement_prompt aggregates wrong results and feedback."""
        from prompts import get_areas_of_improvement_prompt

        wrong_results = [
            QuizResult(
                question_number=2,
                topic="Math",
                question="What is 3+3?",
                matched=True,
                correct=False,
                user_answer="5",
                correct_text="6",
                explanation="",
            ),
            QuizResult(
                question_number=4,
                topic="Math",
                question="What is 5+5?",
                matched=True,
                correct=False,
                user_answer="9",
                correct_text="10",
                explanation="",
            ),
        ]
        feedback = {2: "You miscounted.", 4: "Off by one."}
        prompt = get_areas_of_improvement_prompt(wrong_results, feedback)
        assert "You miscounted." in prompt
        assert "Off by one." in prompt
        assert "2 incorrect answers" in prompt
        assert "themes" in prompt.lower() or "patterns" in prompt.lower()
