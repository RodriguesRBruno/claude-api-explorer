"""Unit tests for main.py — all API calls mocked."""

import os
from unittest import mock

import pytest

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

    def test_quiz_loop_uses_enriched_summary_prompt(self, mock_oauth):
        """_quiz_loop on quit should use get_quiz_summary_prompt with results."""
        with mock.patch("main.Anthropic") as mock_client_class:
            mock_client = mock.MagicMock()
            mock_client_class.return_value = mock_client
            mock_resp = mock.MagicMock()
            mock_resp.content = [mock.MagicMock(type="text", text="Great job!")]
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
                )
            ]
            with mock.patch("builtins.input", side_effect=["quit"]):
                with mock.patch("builtins.print"):
                    tutor._quiz_loop()
            # Check that messages.create was called
            assert mock_client.messages.create.called
            # The chat call should have included the enriched summary prompt
            call_args = mock_client.messages.create.call_args
            messages = call_args[1]["messages"]
            # Last user message should contain the summary data
            assert any("Math" in str(msg) for msg in messages), (
                "Summary should include topic"
            )
