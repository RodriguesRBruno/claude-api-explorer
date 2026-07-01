"""Unit tests for quiz_api.py — all network calls mocked."""

from unittest import mock

import pytest

from quiz_api import (
    FatalQuizApiError,
    execute_tool,
    get_quiz,
    list_quizzes,
    list_topics,
    grade_answer,
)


class TestGetWithRetry:
    """Test _get retry logic and error handling."""

    @mock.patch("quiz_api.httpx.get")
    def test_401_no_retry(self, mock_get):
        """401/403 should raise immediately without retry."""
        mock_get.return_value.status_code = 401
        with pytest.raises(FatalQuizApiError, match="Invalid or missing QUIZ_API_KEY"):
            from quiz_api import _get

            _get("/test", max_retries=3)
        # only 1 call, no retries
        assert mock_get.call_count == 1

    @mock.patch("quiz_api.time.sleep")
    @mock.patch("quiz_api.httpx.get")
    def test_429_retries_then_raises(self, mock_get, mock_sleep):
        """429 should retry up to max_retries, then raise."""
        mock_get.return_value.status_code = 429
        with pytest.raises(FatalQuizApiError, match="Quiz service unavailable"):
            from quiz_api import _get

            _get("/test", max_retries=3)
        # 3 calls total (initial + 2 retries)
        assert mock_get.call_count == 3
        # sleep called 2 times (between 1-2 and 2-3)
        assert mock_sleep.call_count == 2

    @mock.patch("quiz_api.httpx.get")
    def test_200_no_retry(self, mock_get):
        """200 should return immediately."""
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        from quiz_api import _get

        result = _get("/test", max_retries=3)
        assert result is mock_resp
        assert mock_get.call_count == 1

    @mock.patch("quiz_api.time.sleep")
    @mock.patch("quiz_api.httpx.get")
    def test_network_error_retries(self, mock_get, mock_sleep):
        """httpx.RequestError should retry."""
        import httpx

        mock_get.side_effect = httpx.RequestError("Network error")
        with pytest.raises(FatalQuizApiError, match="network error"):
            from quiz_api import _get

            _get("/test", max_retries=2)
        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 1


class TestListTopics:
    """Test list_topics parsing."""

    @mock.patch("quiz_api._get")
    def test_parsing_with_nested_categories(self, mock_get):
        """Should flatten nested categories."""
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = {
            "success": True,
            "data": [
                {
                    "name": "Programming",
                    "slug": "programming",
                    "categories": [
                        {"name": "Python", "slug": "python"},
                        {"name": "JavaScript", "slug": "javascript"},
                    ],
                },
                {
                    "name": "Science",
                    "slug": "science",
                    "categories": [],
                },
            ],
        }
        mock_get.return_value = mock_resp
        result = list_topics()
        assert result["status"] == "ok"
        assert len(result["data"]) == 4
        names = [t["name"] for t in result["data"]]
        assert "Programming" in names
        assert "Python" in names
        assert "JavaScript" in names
        assert "Science" in names

    @mock.patch("quiz_api._get")
    def test_empty_data(self, mock_get):
        """Empty data should return ok with empty list."""
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = {"success": True, "data": []}
        mock_get.return_value = mock_resp
        result = list_topics()
        assert result["status"] == "ok"
        assert result["data"] == []


class TestListQuizzes:
    """Test list_quizzes parsing and no_results."""

    @mock.patch("quiz_api._get")
    def test_success_with_quizzes(self, mock_get):
        """Should return ok with quiz list."""
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = {
            "success": True,
            "data": [
                {"id": "1", "title": "Python Basics", "difficulty": "EASY"},
                {"id": "2", "title": "Python Advanced", "difficulty": "HARD"},
            ],
        }
        mock_get.return_value = mock_resp
        result = list_quizzes(category="Python", difficulty="easy")
        assert result["status"] == "ok"
        assert len(result["data"]) == 2

    @mock.patch("quiz_api._get")
    def test_no_results(self, mock_get):
        """Empty data should return no_results."""
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = {"success": True, "data": []}
        mock_get.return_value = mock_resp
        result = list_quizzes(category="Nonexistent", difficulty="hard")
        assert result["status"] == "no_results"
        assert "No quizzes found" in result["message"]


class TestGetQuiz:
    """Test get_quiz parsing and 404."""

    @mock.patch("quiz_api._get")
    def test_success(self, mock_get):
        """Should return ok with quiz detail."""
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "data": {
                "id": "123",
                "title": "Test Quiz",
                "questions": [{"id": "q1", "text": "What is 2+2?"}],
            },
        }
        mock_get.return_value = mock_resp
        result = get_quiz("123")
        assert result["status"] == "ok"
        assert result["data"]["title"] == "Test Quiz"

    @mock.patch("quiz_api._get")
    def test_404(self, mock_get):
        """404 should return no_results."""
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        result = get_quiz("nonexistent")
        assert result["status"] == "no_results"


class TestExecuteTool:
    """Test tool dispatcher."""

    def test_list_topics_dispatch(self):
        """execute_tool('list_topics', {}) should call list_topics."""
        with mock.patch("quiz_api.list_topics") as mock_func:
            mock_func.return_value = {"status": "ok", "data": []}
            result = execute_tool("list_topics", {})
            mock_func.assert_called_once()
            assert result["status"] == "ok"

    def test_list_quizzes_dispatch(self):
        """execute_tool('list_quizzes', {...}) should call list_quizzes."""
        with mock.patch("quiz_api.list_quizzes") as mock_func:
            mock_func.return_value = {"status": "ok", "data": []}
            result = execute_tool(
                "list_quizzes", {"category": "Python", "difficulty": "EASY"}
            )
            mock_func.assert_called_once_with(category="Python", difficulty="EASY")
            assert result["status"] == "ok"

    def test_get_quiz_dispatch(self):
        """execute_tool('get_quiz', {...}) should call get_quiz."""
        with mock.patch("quiz_api.get_quiz") as mock_func:
            mock_func.return_value = {"status": "ok", "data": {}}
            result = execute_tool("get_quiz", {"quiz_id": "123"})
            mock_func.assert_called_once_with("123")
            assert result["status"] == "ok"

    def test_unknown_tool(self):
        """Unknown tool name should return no_results dict."""
        result = execute_tool("nonexistent_tool", {})
        assert result["status"] == "no_results"
        assert "Unknown tool" in result["message"]


class TestGetQuizLabelInjection:
    """Test that get_quiz injects 'label' field into answers."""

    @mock.patch("quiz_api._get")
    def test_labels_injected(self, mock_get):
        """get_quiz should inject A, B, C, ... labels based on answer order."""
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "data": {
                "id": "123",
                "title": "Test Quiz",
                "questions": [
                    {
                        "id": "q1",
                        "text": "Which is correct?",
                        "answers": [
                            {"id": "a1", "text": "First", "isCorrect": True},
                            {"id": "a2", "text": "Second", "isCorrect": False},
                            {"id": "a3", "text": "Third", "isCorrect": False},
                        ],
                    }
                ],
            },
        }
        mock_get.return_value = mock_resp
        result = get_quiz("123")
        assert result["status"] == "ok"
        question = result["data"]["questions"][0]
        assert len(question["answers"]) == 3
        assert question["answers"][0]["label"] == "A"
        assert question["answers"][1]["label"] == "B"
        assert question["answers"][2]["label"] == "C"


class TestGradeAnswer:
    """Test grade_answer function."""

    def _make_question(self, answers_data):
        """Helper to create a question dict with answers."""
        answers = []
        for i, (text, is_correct) in enumerate(answers_data):
            answers.append(
                {
                    "id": f"a{i}",
                    "text": text,
                    "label": chr(65 + i),
                    "isCorrect": is_correct,
                }
            )
        return {
            "id": "q1",
            "text": "Test question?",
            "answers": answers,
        }

    def test_letter_match_correct(self):
        """Letter match should find the answer by label and grade correctly."""
        question = self._make_question([("Eight", True), ("Nine", False)])
        result = grade_answer(question, "A")
        assert result["matched"] is True
        assert result["correct"] is True
        assert result["selected_text"] == "Eight"
        assert result["correct_text"] == "Eight"

    def test_letter_match_incorrect(self):
        """Letter match should grade as incorrect if the letter's answer is wrong."""
        question = self._make_question([("Eight", True), ("Nine", False)])
        result = grade_answer(question, "B")
        assert result["matched"] is True
        assert result["correct"] is False
        assert result["selected_text"] == "Nine"
        assert result["correct_text"] == "Eight"

    def test_letter_match_case_insensitive(self):
        """Letter match should be case-insensitive."""
        question = self._make_question([("Eight", True), ("Nine", False)])
        result = grade_answer(question, "b")
        assert result["matched"] is True
        assert result["correct"] is False

    def test_letter_match_with_whitespace(self):
        """Letter match should handle leading/trailing whitespace."""
        question = self._make_question([("Eight", True), ("Nine", False)])
        result = grade_answer(question, "  A  ")
        assert result["matched"] is True
        assert result["correct"] is True

    def test_text_match_correct(self):
        """Text match should find exact answer text (case-insensitive)."""
        question = self._make_question([("Eight", True), ("Nine", False)])
        result = grade_answer(question, "eight")
        assert result["matched"] is True
        assert result["correct"] is True
        assert result["selected_text"] == "Eight"

    def test_text_match_incorrect(self):
        """Text match should grade as incorrect if the text's answer is wrong."""
        question = self._make_question([("Eight", True), ("Nine", False)])
        result = grade_answer(question, "nine")
        assert result["matched"] is True
        assert result["correct"] is False
        assert result["correct_text"] == "Eight"

    def test_no_match(self):
        """Unmatched input should return matched=False."""
        question = self._make_question([("Eight", True), ("Nine", False)])
        result = grade_answer(question, "garbage input")
        assert result["matched"] is False
        assert result["correct"] is None
        assert result["selected_text"] == "garbage input"
        assert result["correct_text"] == "Eight"

    def test_letter_takes_precedence_over_text(self):
        """If input starts with a letter, don't try text matching."""
        question = self._make_question([("Eight", False), ("Nine", True)])
        result = grade_answer(question, "A something else")
        assert result["matched"] is True
        assert result["correct"] is False
        assert result["selected_text"] == "Eight"
