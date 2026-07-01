import os
from anthropic import Anthropic, RateLimitError, APIError
from prompts import (
    QUIZ_TUTOR_SYSTEM_PROMPT,
    get_quiz_start_prompt,
    HINT_REQUEST_PROMPT,
    NEXT_QUESTION_PROMPT,
    QUIZ_SUMMARY_PROMPT,
)


class QuizTutor:
    def __init__(self):
        self.client = self._initialize_client()
        self.conversation_history = []
        self.system_prompt = QUIZ_TUTOR_SYSTEM_PROMPT
        self.model = 'claude-haiku-4-5'

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

    def chat(self, user_message):
        """Send a message and get a response, maintaining conversation history"""
        self.conversation_history.append({"role": "user", "content": user_message})

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self.system_prompt,
                messages=self.conversation_history,
            )

            assistant_message = response.content[0].text
            self.conversation_history.append(
                {"role": "assistant", "content": assistant_message}
            )

            return assistant_message

        except RateLimitError as e:
            print(str(e))
            print(
                "\n⚠️  Rate limit reached. Please wait a moment before trying again."
            )
            return None
        except APIError as e:
            print(f"\n❌ API Error: {e}")
            return None

    def start_new_quiz(self):
        """Start a new quiz session"""
        self.conversation_history = []

        print("\n" + "=" * 50)
        print("📚 NEW QUIZ SESSION")
        print("=" * 50)

        topic = input("What topic would you like to be quizzed on? ").strip()
        if not topic:
            print("Topic cannot be empty.")
            return

        difficulty = (
            input("Difficulty level (easy/medium/hard) [default: medium]? ")
            .strip()
            .lower()
        )
        if difficulty not in ["easy", "medium", "hard"]:
            difficulty = "medium"

        num_questions = input("How many questions? [default: 5] ").strip()
        if not num_questions:
            num_questions = "5"
        else:
            try:
                num_questions = str(int(num_questions))
            except ValueError:
                num_questions = "5"

        prompt = get_quiz_start_prompt(topic, difficulty, num_questions)
        response = self.chat(prompt)
        if response:
            print(f"\n{response}\n")
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
    except KeyboardInterrupt:
        print("\n\n👋 Quiz Tutor terminated.")
        return 0


if __name__ == "__main__":
    exit(main())
