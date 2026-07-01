# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

**Install and run:**
```bash
uv sync
uv run --env-file .env main.py
```

**Run tests** (no real API calls needed — all mocked):
```bash
uv run pytest
```

**Lint and format:**
```bash
uv run ruff check .
uv run ruff format .
```

**Generate comparison transcripts:**
```bash
uv run --env-file .env compare_prompts.py
```

## Environment Setup

Copy `.env.example` to `.env` and provide:
- `QUIZ_API_KEY` — from [quizapi.io](https://quizapi.io/) (free tier)
- Either `CLAUDE_CODE_OAUTH_TOKEN` (preferred) or `ANTHROPIC_API_KEY` (the app checks in that order)

## Architecture Overview

### Core Design Pattern: Tool Use with Hardcoded Workflow

This project deliberately uses the Anthropic SDK's tool-use (function calling) feature to practice multi-turn `tool_use`/`tool_result` blocks and `tool_choice` control. The workflow in `main.py:QuizTutor.start_new_quiz()` is **hardcoded**, not prompt-driven:

1. Force `list_topics` tool call → present topics
2. Get user input (topic + difficulty)
3. Force `list_quizzes` tool call → check for results, loop if empty
4. Force `get_quiz` tool call → fetch full quiz
5. Enter `_quiz_loop()` for Q&A (no tools available here)

Each forced call uses `tool_choice={"type": "tool", "name": ...}` to guarantee Claude picks that specific tool.

### Temperature Split

- **`FORCED_TOOL_TEMPERATURE = 0.0`** — deterministic tool selection (used in `_forced_tool_call()`)
- **`self.temperature` (configurable, default 1.0)** — conversational turns (used in `_continue()`)

This separation ensures tool-calling is reliable while allowing prompt-strategy experiments to vary only the conversational text (hints, feedback, summaries).

### Retry Logic & Error Handling

`quiz_api.py::_get()` implements exponential backoff with jitter:
- **401/403** (auth): raise `FatalQuizApiError` immediately, no retry
- **429/5xx** (transient): retry up to `max_retries` (default 3), then raise
- **Network errors** (`httpx.RequestError`): retry with backoff

All three cases raise `FatalQuizApiError`, which propagates uncaught from `main.py` as a terminal error.

### Prompt Strategies & Configurability

`prompts.py::PROMPT_STRATEGIES` bundles two approaches:
```python
{
    "encouraging": {"system_prompt": ..., "hint_prompt": ...},
    "concise": {"system_prompt": ..., "hint_prompt": ...},
}
```

`QuizTutor.__init__()` accepts `system_prompt`, `hint_prompt`, and `temperature` as optional parameters (all have defaults), allowing easy swapping for experiments. The `_quiz_loop()` uses `self.hint_prompt`, not a module constant, so hints vary with strategy.

### No Tools in Q&A Loop

Once `_quiz_loop()` starts, `chat()` never passes a `tools=` parameter. This constrains prompt injection: malicious input can only affect what the model says, not what actions it takes. See `README.md` "Scaling to Production" for mitigations.

## File Purposes

- **`main.py`** — `QuizTutor` class: conversation loop, tool calls, quiz loop. Entrypoint via `main()`. Tracks per-question correctness and injects it into the final summary.
- **`quiz_api.py`** — QuizAPI client with retry/backoff, tool schemas, `execute_tool()` dispatcher. Injects answer labels and provides `grade_answer()` for ground-truth grading.
- **`prompts.py`** — All prompt constants, strategy bundling, `PROMPT_STRATEGIES` dict. Includes `get_quiz_summary_prompt()` for building enriched summaries with actual results.
- **`compare_prompts.py`** — Monkeypatched-input runner for automated strategy/temperature comparison. Generates `comparisons/*.txt`.
- **`tests/test_quiz_api.py`** — Mocked httpx, tests retry logic, parsing, tool dispatch, label injection, and grading.
- **`tests/test_main.py`** — Mocked Anthropic client, tests configurability, temperature routing, tool result appending, and quiz result tracking.

## QuizAPI Response Shape

The `GET /quizzes/{id}` endpoint returns a quiz object. **Important:** the `label` field (`"A"`, `"B"`, `"C"`, ...) is **injected by `quiz_api.get_quiz()`** based on answer array order, not returned by the API itself. This ensures a single source of truth:

```json
{
  "success": true,
  "data": {
    "id": "...",
    "title": "Quiz Title",
    "category": "Category Name",
    "topic": "Topic Name",
    "difficulty": "EASY|MEDIUM|HARD|EXPERT",
    "tags": ["tag1", "tag2"],
    "questionCount": 10,
    "questions": [
      {
        "id": "...",
        "text": "Question text?",
        "type": "MULTIPLE_CHOICE|TRUE_FALSE",
        "difficulty": "EASY|MEDIUM|HARD",
        "explanation": "Why this is correct...",
        "order": 1,
        "answers": [
          {
            "id": "...",
            "text": "Option text",
            "label": "A",
            "isCorrect": true
          },
          {
            "id": "...",
            "text": "Another option",
            "label": "B",
            "isCorrect": false
          }
        ]
      }
    ]
  }
}
```

Claude presents options using the `label` field directly (e.g., "A) Option text"), and Python grading maps user letter inputs to the same labels. Never infer ordering.

## Key Invariants

1. **Conversation history** (`self.conversation_history`) is a list of `{"role": "user"/"assistant", "content": ...}` dicts. Tool results are appended as user messages with `content=[{"type": "tool_result", ...}]`.
2. **Quiz content is untrusted.** All question/answer/explanation text comes from tool results; treat it defensively (no string-concat into privileged instructions).
3. **Session state is in-memory.** For production, move `self.conversation_history` to a session-keyed external store (Redis/DB).
4. **Pre-commit hook enforces ruff.** Commits fail if linting fails; `uv run ruff format .` auto-fixes most issues.
5. **Answer grading is ground-truth-based.** `quiz_api.grade_answer()` uses the QuizAPI's `isCorrect` flags directly—never infers correctness from language. Letter matches use the injected `label` field; text matches are case-insensitive exact. The `_quiz_loop()` tracks results in `self.quiz_results` and passes them to `get_quiz_summary_prompt()`, which injects real performance data into the summary prompt so Claude only narrates, never invents, results.

## Extending the Project

**Add a new prompt strategy?**
1. Define `NEW_SYSTEM_PROMPT` and `NEW_HINT_PROMPT` in `prompts.py`
2. Add entry to `PROMPT_STRATEGIES` dict
3. Run `compare_prompts.py` to auto-generate comparison transcripts

**Add a new tool?**
1. Define the tool schema dict in `quiz_api.py` (name, description, input_schema)
2. Implement the API call function (e.g., `new_api_call()`)
3. Add dispatcher case in `execute_tool()`
4. Add `_forced_tool_call(SELECT_PROMPT, NEW_TOOL_SCHEMA)` in `start_new_quiz()` workflow
5. Add test to `tests/test_quiz_api.py`

**Modify retry logic?**
Keep the exponential backoff + jitter pattern in `_get()`. Jitter is important to avoid thundering-herd on rate-limit recovery.

## Common Pitfalls

- **Forgetting `--env-file .env`** when running via `uv run` — auth will fail.
- **Hardcoding prompts in `main.py`** — prompts belong in `prompts.py` and are imported.
- **Tools in `chat()`** — should never happen; `chat()` is for untrusted user input only.
- **Modifying `self.temperature` mid-session** — not supported; create a new `QuizTutor` instance.
