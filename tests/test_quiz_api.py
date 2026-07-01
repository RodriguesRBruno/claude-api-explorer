"""Unit tests for quiz_api.py — all network calls mocked."""

from unittest import mock

import pytest

from quiz_api import (
    FatalQuizApiError,
    execute_tool,
    get_quiz,
    list_quizzes,
    list_topics,
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
