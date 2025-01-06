import os
import re
from typing import List, Tuple

# import openai
from github import Github

import google.generativeai as genai


class CodeReviewBot:
    def __init__(self, github_token: str, gemini_api_key: str):
        """
        Initialize the code review bot with necessary credentials

        Args:
            github_token (str): GitHub personal access token
            openai_api_key (str): OpenAI API key for code analysis
        """
        self.github = Github(github_token)
        genai.configure(api_key=gemini_api_key)

    def get_pull_request_changes(
        self, repo_name: str, pr_number: int
    ) -> List[Tuple[str, str, List[str]]]:
        """
        Get the changes from a pull request

        Returns:
            List of tuples containing (file_name, file_content, changed_lines)
        """
        repo = self.github.get_repo(repo_name)
        pull_request = repo.get_pull(pr_number)
        files = pull_request.get_files()

        changes = []
        for file in files:
            if file.filename.endswith(
                (".py", ".js", ".ts", ".java", ".cpp", ".jsx", ".tsx")
            ):
                patch = file.patch
                changed_lines = self._extract_changed_lines(patch)
                content = repo.get_contents(
                    file.filename, ref=pull_request.head.sha
                ).decoded_content.decode()
                changes.append((file.filename, content, changed_lines))

        return changes

    def _extract_changed_lines(self, patch: str) -> List[str]:
        """Extract the actual changed lines from a patch"""
        changed_lines = []
        for line in patch.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                changed_lines.append(line[1:].strip())
        return changed_lines

    def analyze_code(self, code: str, changed_lines: List[str]) -> List[dict]:
        """
        Analyze code using OpenAI's API to generate review comments

        Returns:
            List of dictionaries containing review comments and their positions
        """

        changed_lines_combined = "\n".join(changed_lines)

        prompt = f"""
        Review the following code changes and provide specific, actionable feedback.
        Focus on:
        - Code quality and best practices
        - Potential bugs or security issues
        - Performance improvements
        - Readability and maintainability
        
        Changed lines:
        {changed_lines_combined}
        
        Full context:
        {code}
        
        Provide feedback in a structured format.
        """

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)

        print(response.text)

        # Parse the response and generate structured feedback
        feedback = self._parse_ai_feedback(response.text)

        # Parse the response and generate structured feedback
        # feedback = self._parse_ai_feedback(response.choices[0].text)
        return feedback

    def _parse_ai_feedback(self, feedback_text: str) -> List[dict]:
        """Parse AI feedback into structured format"""
        # Simple parsing logic - can be enhanced based on AI response format
        comments = []
        for line in feedback_text.split("\n"):
            if line.strip():
                comments.append(
                    {
                        "body": line.strip(),
                        "position": None,  # You might want to implement position detection
                    }
                )
        return comments

    def post_review_comments(
        self, repo_name: str, pr_number: int, comments: List[dict]
    ):
        """Post review comments on the pull request"""
        repo = self.github.get_repo(repo_name)
        pull_request = repo.get_pull(pr_number)
        commit = repo.get_commit(pull_request.head.sha)

        for comment in comments:
            pull_request.create_review_comment(
                body=comment["body"],
                commit=commit,
                path=comment.get("path", ""),
                line=comment.get("line", 0),
                # side=comment.get("side", "RIGHT"),
                # start_line=comment.get("start_line", None),
                # start_side=comment.get("start_side", None),
                # in_reply_to=comment.get("in_reply_to", None),
                # subject_type=comment.get("subject_type", None),
                # as_suggestion=comment.get("as_suggestion", False),
            )


def main():
    # Load environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    repo_name = os.getenv("GITHUB_REPOSITORY")
    pr_number = int(os.getenv("GITHUB_PR_NUMBER"))

    print(
        f"Environment variables: {github_token}, {gemini_api_key}, {repo_name}, {pr_number}"
    )

    print(github_token, gemini_api_key, repo_name, pr_number)

    if not all([github_token, gemini_api_key, repo_name, pr_number]):
        raise ValueError("Missing required environment variables")

    # Initialize and run the bot
    bot = CodeReviewBot(github_token, gemini_api_key)

    # Get changes from the pull request
    changes = bot.get_pull_request_changes(repo_name, pr_number)

    # Analyze each changed file and post comments
    for filename, content, changed_lines in changes:
        review_comments = bot.analyze_code(content, changed_lines)
        bot.post_review_comments(repo_name, pr_number, review_comments)


if __name__ == "__main__":
    main()
