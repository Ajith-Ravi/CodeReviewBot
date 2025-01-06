import os
import re
from typing import List, Tuple, Optional
from github import Github
import google.generativeai as genai
from github.PullRequest import PullRequest
from github.Repository import Repository
from github.ContentFile import ContentFile


class CodeReviewBot:
    def __init__(self, github_token: str, gemini_api_key: str):
        """
        Initialize the code review bot with necessary credentials

        Args:
            github_token (str): GitHub personal access token
            gemini_api_key (str): Gemini API key for code analysis
        """
        self.github = Github(github_token)
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel(
            "gemini-1.5-pro"
        )  # Using pro model for better code analysis

    def get_pull_request_changes(
        self, repo_name: str, pr_number: int
    ) -> List[Tuple[str, str, List[str], List[int]]]:
        """
        Get the changes from a pull request

        Args:
            repo_name (str): Name of the repository in format 'owner/repo'
            pr_number (int): Pull request number

        Returns:
            List of tuples containing (file_name, file_content, changed_lines, line_numbers)
        """
        try:
            repo = self.github.get_repo(repo_name)
            pull_request = repo.get_pull(pr_number)
            files = pull_request.get_files()

            changes = []
            for file in files:
                if file.filename.endswith(
                    (".py", ".js", ".ts", ".java", ".cpp", ".jsx", ".tsx")
                ):
                    patch = file.patch
                    changed_lines, line_numbers = self._extract_changed_lines(patch)
                    try:
                        content = repo.get_contents(
                            file.filename, ref=pull_request.head.sha
                        ).decoded_content.decode("utf-8")
                        changes.append(
                            (file.filename, content, changed_lines, line_numbers)
                        )
                    except (AttributeError, UnicodeDecodeError) as e:
                        print(f"Error reading file {file.filename}: {e}")
                        continue

            return changes
        except Exception as e:
            print(f"Error getting pull request changes: {e}")
            return []

    def _extract_changed_lines(self, patch: str) -> Tuple[List[str], List[int]]:
        """
        Extract the actual changed lines and their line numbers from a patch

        Args:
            patch (str): Git patch string

        Returns:
            Tuple of (changed_lines, line_numbers)
        """
        changed_lines = []
        line_numbers = []
        current_line = 0

        for line in patch.split("\n"):
            if line.startswith("@@"):
                # Parse the @@ line to get the starting line number
                match = re.search(r"\+(\d+)", line)
                if match:
                    current_line = int(match.group(1)) - 1
                continue

            current_line += 1
            if line.startswith("+") and not line.startswith("+++"):
                changed_lines.append(line[1:].strip())
                line_numbers.append(current_line)

        return changed_lines, line_numbers

    def analyze_code(
        self, filename: str, code: str, changed_lines: List[str]
    ) -> List[dict]:
        """
        Analyze code using Gemini's API to generate review comments

        Args:
            filename (str): Name of the file being analyzed
            code (str): Full file content
            changed_lines (List[str]): List of changed lines

        Returns:
            List of dictionaries containing review comments and their positions
        """
        try:
            changed_lines_combined = "\n".join(changed_lines)
            file_extension = os.path.splitext(filename)[1]

            prompt = f"""
            You are a senior developer reviewing code changes in a {file_extension} file.
            Please review the following code changes and provide specific, actionable feedback.
            Focus on:
            - Code quality and best practices
            - Potential bugs or security issues
            - Performance improvements
            - Readability and maintainability

            File: {filename}
            
            Changed lines:
            ```{file_extension}
            {changed_lines_combined}
            ```
            
            Full context:
            ```{file_extension}
            {code}
            ```
            
            Provide each piece of feedback in the following format:
            ISSUE: [Brief description of the issue]
            LOCATION: [Relevant code snippet or line reference]
            SUGGESTION: [Specific suggestion for improvement]
            ---
            """

            response = self.model.generate_content(prompt)
            return self._parse_ai_feedback(response.text)

        except Exception as e:
            print(f"Error analyzing code: {e}")
            return []

    def _parse_ai_feedback(self, feedback_text: str) -> List[dict]:
        """
        Parse AI feedback into structured format

        Args:
            feedback_text (str): Raw feedback from Gemini

        Returns:
            List of dictionaries containing parsed feedback
        """
        comments = []
        current_comment = {}

        for line in feedback_text.split("\n"):
            line = line.strip()
            if not line or line == "---":
                if current_comment.get("body"):
                    comments.append(current_comment)
                    current_comment = {}
                continue

            if line.startswith("ISSUE:"):
                current_comment["body"] = line[6:].strip()
            elif line.startswith("LOCATION:"):
                current_comment["location"] = line[9:].strip()
            elif line.startswith("SUGGESTION:"):
                current_comment["body"] = (
                    current_comment.get("body", "")
                    + "\n\nSuggestion: "
                    + line[11:].strip()
                )

        if current_comment.get("body"):
            comments.append(current_comment)

        return comments

    def post_review_comments(
        self,
        repo_name: str,
        pr_number: int,
        filename: str,
        comments: List[dict],
        line_numbers: List[int],
    ):
        """
        Post review comments on the pull request

        Args:
            repo_name (str): Repository name
            pr_number (int): Pull request number
            filename (str): File being reviewed
            comments (List[dict]): List of review comments
            line_numbers (List[int]): List of line numbers for changed lines
        """
        try:
            repo = self.github.get_repo(repo_name)
            pull_request = repo.get_pull(pr_number)

            # Create a review instance
            review_comments = []

            for comment in comments:
                # Try to match the location to a line number
                target_line = line_numbers[0]  # Default to first changed line
                if "location" in comment:
                    # Try to find the closest matching line number
                    for line_num in line_numbers:
                        if str(line_num) in comment["location"]:
                            target_line = line_num
                            break

                review_comments.append(
                    {"path": filename, "position": target_line, "body": comment["body"]}
                )

            # Submit all comments as a single review
            if review_comments:
                pull_request.create_review(
                    commit=pull_request.get_commits().reversed[0],
                    comments=review_comments,
                    event="COMMENT",
                )

        except Exception as e:
            print(f"Error posting review comments: {e}")


def main():
    # Load environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    repo_name = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("GITHUB_PR_NUMBER")

    # Validate environment variables
    if not all([github_token, gemini_api_key, repo_name, pr_number]):
        raise ValueError("Missing required environment variables")

    try:
        pr_number = int(pr_number)
    except ValueError:
        raise ValueError("GITHUB_PR_NUMBER must be an integer")

    # Initialize and run the bot
    bot = CodeReviewBot(github_token, gemini_api_key)

    # Get changes from the pull request
    changes = bot.get_pull_request_changes(repo_name, pr_number)

    # Analyze each changed file and post comments
    for filename, content, changed_lines, line_numbers in changes:
        review_comments = bot.analyze_code(filename, content, changed_lines)
        if review_comments:
            bot.post_review_comments(
                repo_name, pr_number, filename, review_comments, line_numbers
            )


if __name__ == "__main__":
    main()
