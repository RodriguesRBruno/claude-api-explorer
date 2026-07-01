import os
import json
from anthropic import Anthropic, RateLimitError, APIError
from prompts import (
    QUIZ_TUTOR_SYSTEM_PROMPT,
    get_list_quizzes_prompt,
    TOPIC_LIST_REQUEST_PROMPT,
    SELECT_QUIZ_PROMPT,
    HINT_REQUEST_PROMPT,
    NEXT_QUESTION_PROMPT,
    QUIZ_SUMMARY_PROMPT,
)
from quiz_api import (
    LIST_TOPICS_TOOL,
    LIST_QUIZZES_TOOL,
    GET_QUIZ_TOOL,
    execute_tool,
    FatalQuizApiError,
)


class QuizTutor:
    def __init__(self):
        self.client = self._initialize_client()
        self.conversation_history = []
        self.system_prompt = QUIZ_TUTOR_SYSTEM_PROMPT
        self.model = "claude-haiku-4-5"

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

            self._forced_tool_call(SELECT_QUIZ_PROMPT, GET_QUIZ_TOOL)
            first_question_text = self._continue()
            if first_question_text is None:
                return
            print(f"\n{first_question_text}\n")
            break

        self._quiz_loop()

    def _quiz_loop(self):
        """Interactive loop for answering quiz questions"""
        while True:
            user_input = input(
                "Your answer (or 'hint' for hint, 'next' to skip, 'quit' to end): "
            ).strip()

            if not user_input:
                continue

            if user_input.lower() == "quit":
                response = self.chat(QUIZ_SUMMARY_PROMPT)
                if response:
                    print(f"\n📊 QUIZ SUMMARY:\n{response}\n")
                break

            elif user_input.lower() == "hint":
                response = self.chat(HINT_REQUEST_PROMPT)
                if response:
                    print(f"\n💡 Hint: {response}\n")

            elif user_input.lower() == "next":
                response = self.chat(NEXT_QUESTION_PROMPT)
                if response:
                    print(f"\n{response}\n")

            else:
                response = self.chat(user_input)
                if response:
                    print(f"\n{response}\n")

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
