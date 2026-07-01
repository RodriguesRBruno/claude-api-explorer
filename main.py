import os
import json
from anthropic import Anthropic, RateLimitError, APIError
from prompts import (
    QUIZ_TUTOR_SYSTEM_PROMPT,
    QUIZ_SUMMARY_PROMPT,
    get_list_quizzes_prompt,
    TOPIC_LIST_REQUEST_PROMPT,
    SELECT_QUIZ_PROMPT,
    HINT_REQUEST_PROMPT,
    NEXT_QUESTION_PROMPT,
    get_question_feedback_prompt,
    get_areas_of_improvement_prompt,
)
from quiz_api import (
    LIST_TOPICS_TOOL,
    LIST_QUIZZES_TOOL,
    GET_QUIZ_TOOL,
    execute_tool,
    grade_answer,
    FatalQuizApiError,
)
from quiz_result import QuizResult


FORCED_TOOL_TEMPERATURE = 0.0


class QuizTutor:
    def __init__(
        self,
        system_prompt=QUIZ_TUTOR_SYSTEM_PROMPT,
        hint_prompt=HINT_REQUEST_PROMPT,
        temperature=1.0,
    ):
        self.client = self._initialize_client()
        self.conversation_history = []
        self.system_prompt = system_prompt
        self.hint_prompt = hint_prompt
        self.temperature = temperature
        self.model = "claude-haiku-4-5"
        self.quiz_questions = []
        self.quiz_topic = ""
        self.current_question_index = 0
        self.quiz_results = []

    def _initialize_client(self):
        """Initialize Anthropic client with OAuth token or API key"""
        oauth_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
        api_key = os.getenv("ANTHROPIC_API_KEY")

        if oauth_token:
            print("✓ Using OAuth token for authentication")
            return Anthropic(auth_token=oauth_token)
        elif api_key:
            print("✓ Using API key for authentication")
            return Anthropic(api_key=api_key)
        else:
            raise ValueError(
                "No authentication method found. Please set either:\n"
                "  - CLAUDE_CODE_OAUTH_TOKEN in .env file, or\n"
                "  - ANTHROPIC_API_KEY in .env file or environment"
            )

    def _continue(self):
        """Get the next assistant turn from existing history (no new user message).
        Used right after appending a tool_result, or by chat()."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self.system_prompt,
                messages=self.conversation_history,
                temperature=self.temperature,
            )
            self.conversation_history.append(
                {"role": "assistant", "content": response.content}
            )
            return next((b.text for b in response.content if b.type == "text"), "")
        except RateLimitError as e:
            print(str(e))
            print("\n⚠️  Rate limit reached. Please wait a moment before trying again.")
            return None
        except APIError as e:
            print(f"\n❌ API Error: {e}")
            return None

    def _isolated_completion(self, prompt: str) -> str | None:
        """One-off completion isolated from conversation_history — used for
        per-question feedback and areas-of-improvement synthesis so the noisy
        full transcript can't leak into or bias these outputs. No tools, no
        history pollution."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=self.system_prompt,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
            )
            return next((b.text for b in response.content if b.type == "text"), "")
        except RateLimitError as e:
            print(str(e))
            print("\n⚠️  Rate limit reached generating feedback.")
            return None
        except APIError as e:
            print(f"\n❌ API Error generating feedback: {e}")
            return None

    def chat(self, user_message):
        """Plain conversational turn — no tools available.
        Used by hint/next/quit/answer loops."""
        self.conversation_history.append({"role": "user", "content": user_message})
        return self._continue()

    def _forced_tool_call(self, user_message, tool_schema):
        """Send user_message, forcing Claude to call exactly tool_schema['name'].
        Executes the tool, appends the tool_result, and returns the result dict.
        FatalQuizApiError (auth/retry-exhausted) propagates uncaught."""
        self.conversation_history.append({"role": "user", "content": user_message})
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self.system_prompt,
            messages=self.conversation_history,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_schema["name"]},  # type: ignore
            temperature=FORCED_TOOL_TEMPERATURE,
        )
        self.conversation_history.append(
            {"role": "assistant", "content": response.content}
        )
        tool_use_block = next(b for b in response.content if b.type == "tool_use")
        result = execute_tool(tool_use_block.name, tool_use_block.input)
        self.conversation_history.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": json.dumps(result),
                    }
                ],
            }
        )
        return result

    def start_new_quiz(self):
        """Start a new quiz session with hardcoded tool-use workflow:
        1. Force list_topics call
        2. Present topics
        3. Get user topic/difficulty
        4. Force list_quizzes call
        5. If no results, loop back to step 3
        6. Force get_quiz call (Claude picks a quiz)
        7. Present first question
        8. Enter hint/next/answer loop"""
        self.conversation_history = []

        print("\n" + "=" * 50)
        print("📚 NEW QUIZ SESSION")
        print("=" * 50)

        self._forced_tool_call(TOPIC_LIST_REQUEST_PROMPT, LIST_TOPICS_TOOL)
        topics_text = self._continue()
        if topics_text is None:
            return
        print(f"\n{topics_text}\n")

        while True:
            topic = input("What topic would you like to be quizzed on? ").strip()
            if not topic:
                print("Topic cannot be empty.")
                continue

            difficulty = (
                input("Difficulty level (easy/medium/hard) [default: medium]? ")
                .strip()
                .lower()
            )
            if difficulty not in ["easy", "medium", "hard"]:
                difficulty = "medium"

            quizzes_result = self._forced_tool_call(
                get_list_quizzes_prompt(topic, difficulty), LIST_QUIZZES_TOOL
            )

            if quizzes_result["status"] == "no_results":
                print(
                    f"\nNo quizzes found for '{topic}' at {difficulty} difficulty. "
                    f"Let's pick another topic.\n"
                )
                continue

            quiz_result = self._forced_tool_call(SELECT_QUIZ_PROMPT, GET_QUIZ_TOOL)
            self.quiz_questions = quiz_result.get("data", {}).get("questions", [])
            self.quiz_topic = (
                quiz_result.get("data", {}).get("topic")
                or quiz_result.get("data", {}).get("category")
                or ""
            )
            self.current_question_index = 0
            self.quiz_results = []
            first_question_text = self._continue()
            if first_question_text is None:
                return
            print(f"\n{first_question_text}\n")
            break

        self._quiz_loop()

    def _build_quiz_summary(self) -> str:
        """Build a comprehensive summary of quiz performance with per-question
        isolation: correct answers need no Claude call, each wrong answer gets
        its own isolated feedback call, and a final call synthesizes areas of
        improvement from the misses only."""
        if not self.quiz_results:
            fallback = self.chat(QUIZ_SUMMARY_PROMPT)
            return fallback or "(Unable to generate summary at this time)"

        wrong_results = [r for r in self.quiz_results if not (r.matched and r.correct)]

        feedback_by_question: dict[int, str | None] = {
            r.question_number: self._isolated_completion(
                get_question_feedback_prompt(r)
            )
            for r in wrong_results
        }

        lines = ["📊 Here's how you did:\n"]

        for result in self.quiz_results:
            if result.matched and result.correct:
                lines.append(
                    f"{result.question_number}. {result.question}\n   ✓ Correct\n"
                )
                continue

            status = "✗ Incorrect" if result.matched else "❓ Unverified"
            lines.append(
                f"{result.question_number}. {result.question}\n"
                f"   {status}\n"
                f"   Your answer: {result.user_answer}\n"
                f"   Correct answer: {result.correct_text}\n"
            )

            feedback = feedback_by_question.get(result.question_number)
            if feedback:
                lines.append(f"   Feedback: {feedback}\n")
            else:
                lines.append(
                    "   Feedback: (unable to generate feedback for this question)\n"
                )

        if wrong_results:
            filtered_feedback = {
                k: v for k, v in feedback_by_question.items() if v is not None
            }
            improvement = self._isolated_completion(
                get_areas_of_improvement_prompt(wrong_results, filtered_feedback)  # type: ignore
            )
            if improvement:
                lines.append(f"\n📈 Areas for improvement:\n{improvement}\n")
            else:
                lines.append(
                    "\n📈 Areas for improvement: (unable to generate at this time)\n"
                )
        else:
            lines.append("\n🎉 Perfect score — no areas of improvement needed!\n")

        return "".join(lines)

    def _get_valid_answer_options(self) -> list[str]:
        """Get list of valid answer letter options (A, B, C, ...) for current question."""
        if self.current_question_index >= len(self.quiz_questions):
            return []
        current_question = self.quiz_questions[self.current_question_index]
        return [a.get("label", "") for a in current_question.get("answers", [])]

    def _is_valid_answer(self, user_input: str) -> bool:
        """Check if user input is a valid answer option, 'hint', or 'quit'."""
        lower_input = user_input.lower()
        if lower_input in ("hint", "quit"):
            return True
        valid_options = self._get_valid_answer_options()
        return user_input.upper() in valid_options

    def _get_invalid_answer_message(self) -> str:
        """Generate error message listing valid options."""
        valid_options = self._get_valid_answer_options()
        if not valid_options:
            return "No valid options available. Type 'quit' to end the quiz."
        options_str = ", ".join(valid_options)
        return (
            f"Invalid response. Please enter one of: {options_str}, 'hint', or 'quit'."
        )

    def _quiz_loop(self):
        """Interactive loop for answering quiz questions.
        Automatically advances to the next question after each answer.
        Users can request hints or quit at any time.
        Tracks per-question correctness using the QuizAPI's ground truth.
        Validates that answers match one of the presented options."""
        while True:
            user_input = input(
                "Your answer (or 'hint' for hint, 'quit' to end): "
            ).strip()

            if not user_input:
                continue

            if not self._is_valid_answer(user_input):
                print(f"\n❌ {self._get_invalid_answer_message()}\n")
                continue

            if user_input.lower() == "quit":
                summary = self._build_quiz_summary()
                if summary:
                    print(f"\n📊 QUIZ SUMMARY:\n{summary}\n")
                break

            elif user_input.lower() == "hint":
                response = self.chat(self.hint_prompt)
                if response:
                    print(f"\n💡 Hint: {response}\n")

            else:
                if self.current_question_index < len(self.quiz_questions):
                    current_question = self.quiz_questions[self.current_question_index]
                    grade_result = grade_answer(current_question, user_input)
                    self.quiz_results.append(
                        QuizResult(
                            question_number=self.current_question_index + 1,
                            topic=self.quiz_topic,
                            question=current_question.get("text", ""),
                            matched=grade_result.get("matched", False),
                            correct=grade_result.get("correct"),
                            user_answer=grade_result.get("selected_text", ""),
                            correct_text=grade_result.get("correct_text", ""),
                            explanation=current_question.get("explanation", "") or "",
                        )
                    )
                    self.current_question_index += 1

                response = self.chat(user_input)
                if response:
                    print(f"\n{response}\n")
                next_q = self.chat(NEXT_QUESTION_PROMPT)
                if next_q:
                    print(f"{next_q}\n")

    def run(self):
        """Main application loop"""
        print("\n" + "=" * 50)
        print("🎓 QUIZ TUTOR - Powered by Claude API")
        print("=" * 50)
        print("\nLearn effectively with AI-powered interactive quizzes!\n")

        while True:
            print("Options:")
            print("  1. Start a new quiz")
            print("  2. Exit")

            choice = input("\nChoose an option (1-2): ").strip()

            if choice == "1":
                self.start_new_quiz()
            elif choice == "2":
                print("\n👋 Thanks for learning with Quiz Tutor! See you next time.\n")
                break
            else:
                print("❌ Invalid choice. Please enter 1 or 2.\n")


def main():
    try:
        tutor = QuizTutor()
        tutor.run()
        return 0
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    except FatalQuizApiError as e:
        print(f"❌ {e}")
        return 1
    except KeyboardInterrupt:
        print("\n\n👋 Quiz Tutor terminated.")
        return 0


if __name__ == "__main__":
    exit(main())
