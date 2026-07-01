"""Quiz API client for fetching real quiz content from quizapi.io."""

import os
import time
import random
import httpx


BASE_URL = "https://quizapi.io/api/v1"


class FatalQuizApiError(Exception):
    """Raised for auth failures and retry-exhausted errors — both cases
    require the app to terminate (print error and exit(1))."""

    pass


def _headers() -> dict:
    """Build Authorization header from QUIZ_API_KEY env var."""
    api_key = os.getenv("QUIZ_API_KEY", "")
    return {"Authorization": f"Bearer {api_key}"}


def _get(path: str, params: dict | None = None, max_retries: int = 3) -> httpx.Response:
    """
    GET {BASE_URL}{path} with Authorization header.
    Raises FatalQuizApiError for auth failure (401/403) and for retry-exhausted
    transient errors (429, 5xx, network failures).
    Otherwise returns the raw response — caller interprets status codes.
    """
    for attempt in range(max_retries):
        try:
            resp = httpx.get(
                f"{BASE_URL}{path}",
                headers=_headers(),
                params=params,
                timeout=10.0,
            )
        except httpx.RequestError:
            if attempt == max_retries - 1:
                raise FatalQuizApiError(
                    "Quiz service unavailable — network error after retries."
                )
            sleep_for = min(2**attempt, 8) + random.uniform(0, 0.5)
            time.sleep(sleep_for)
            continue

        if resp.status_code in (401, 403):
            raise FatalQuizApiError(
                "Invalid or missing QUIZ_API_KEY. Please set a valid QUIZ_API_KEY in .env."
            )

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_retries - 1:
                raise FatalQuizApiError(
                    f"Quiz service unavailable (HTTP {resp.status_code}) after retries."
                )
            sleep_for = min(2**attempt, 8) + random.uniform(0, 0.5)
            time.sleep(sleep_for)
            continue

        return resp

    raise FatalQuizApiError("Quiz service unavailable after retries.")


def list_topics() -> dict:
    """
    GET /categories — list available topic/category names.
    Returns {"status": "ok", "data": [{"name": ..., "slug": ...}, ...]}
    Data is defensively extracted to handle both flat and nested structures.
    """
    resp = _get("/categories")
    raw = resp.json()

    topics = []
    if raw.get("success") and raw.get("data"):
        for item in raw["data"]:
            name = item.get("name")
            slug = item.get("slug")
            if name:
                topics.append({"name": name, "slug": slug})

            for sub in item.get("categories", []) or []:
                sub_name = sub.get("name")
                sub_slug = sub.get("slug")
                if sub_name:
                    topics.append({"name": sub_name, "slug": sub_slug})

    return {"status": "ok", "data": topics}


def list_quizzes(
    category: str | None = None, difficulty: str | None = None, limit: int = 10
) -> dict:
    """
    GET /quizzes?category=...&difficulty=...&limit=...
    Lists quizzes, optionally filtered by category and difficulty.
    Returns {"status": "ok", "data": [...]} or {"status": "no_results", ...}
    """
    params = {"limit": limit}
    if category:
        params["category"] = category
    if difficulty:
        params["difficulty"] = difficulty.upper()

    resp = _get("/quizzes", params=params)
    data = resp.json()

    quizzes = []
    if data.get("success") and data.get("data"):
        quizzes = data["data"]

    if not quizzes:
        return {
            "status": "no_results",
            "message": f"No quizzes found for category={category}, difficulty={difficulty}.",
        }

    return {"status": "ok", "data": quizzes}


def get_quiz(quiz_id: int | str) -> dict:
    """
    GET /quizzes/{id}
    Fetch full quiz detail including questions array.
    Returns {"status": "ok", "data": {...}} or {"status": "no_results", ...}
    """
    resp = _get(f"/quizzes/{quiz_id}")

    if resp.status_code == 404:
        return {
            "status": "no_results",
            "message": f"Quiz {quiz_id} not found.",
        }

    data = resp.json()
    if data.get("success") and data.get("data"):
        return {"status": "ok", "data": data["data"]}

    return {
        "status": "no_results",
        "message": f"Quiz {quiz_id} not found.",
    }


LIST_TOPICS_TOOL = {
    "name": "list_topics",
    "description": "List the quiz topics/categories currently available.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

LIST_QUIZZES_TOOL = {
    "name": "list_quizzes",
    "description": (
        "List available quizzes filtered by topic/category and difficulty."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Topic/category name to filter by.",
            },
            "difficulty": {
                "type": "string",
                "enum": ["EASY", "MEDIUM", "HARD", "EXPERT"],
                "description": "Difficulty level to filter by.",
            },
        },
        "required": ["category", "difficulty"],
    },
}

GET_QUIZ_TOOL = {
    "name": "get_quiz",
    "description": (
        "Fetch full detail for a quiz by ID, including questions, answers, and explanations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "quiz_id": {
                "type": ["string", "integer"],
                "description": "The id of the quiz to fetch.",
            },
        },
        "required": ["quiz_id"],
    },
}

TOOLS = [LIST_TOPICS_TOOL, LIST_QUIZZES_TOOL, GET_QUIZ_TOOL]


def execute_tool(name: str, tool_input: dict) -> dict:
    """
    Execute a tool by name and return its result dict.
    Raises FatalQuizApiError for auth/retry-exhausted errors (propagates up).
    Returns a status dict ({"status": "ok"/"no_results", ...}) for normal outcomes.
    """
    if name == "list_topics":
        return list_topics()
    elif name == "list_quizzes":
        return list_quizzes(
            category=tool_input.get("category"),
            difficulty=tool_input.get("difficulty"),
        )
    elif name == "get_quiz":
        return get_quiz(tool_input.get("quiz_id"))
    else:
        return {
            "status": "no_results",
            "message": f"Unknown tool: {name}",
        }
