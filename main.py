import os
import re
from typing import List, Tuple, Optional, Dict
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
            github_token (str): GitHub App installation token or PAT
            gemini_api_key (str): Gemini API key for code analysis
        """
        self.github = Github(github_token)
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel("gemini-1.5-pro")

    def get_pull_request_changes(
        self, repo_name: str, pr_number: int
    ) -> List[Tuple[str, str, Dict[int, str], List[int]]]:
        """
        Get the changes from a pull request

        Args:
            repo_name (str): Name of the repository in format 'owner/repo'
            pr_number (int): Pull request number

        Returns:
            List of tuples containing (file_name, file_content, changed_lines_dict, line_numbers)
            where changed_lines_dict maps line numbers to their content
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
                    changed_lines_dict, line_numbers = self._extract_changed_lines(
                        patch
                    )
                    try:
                        content = repo.get_contents(
                            file.filename, ref=pull_request.head.sha
                        ).decoded_content.decode("utf-8")
                        changes.append(
                            (file.filename, content, changed_lines_dict, line_numbers)
                        )
                    except (AttributeError, UnicodeDecodeError) as e:
                        print(f"Error reading file {file.filename}: {e}")
                        continue

            return changes
        except Exception as e:
            print(f"Error getting pull request changes: {e}")
            return []

    def _extract_changed_lines(self, patch: str) -> Tuple[Dict[int, str], List[int]]:
        """
        Extract the actual changed lines and their line numbers from a patch

        Args:
            patch (str): Git patch string

        Returns:
            Tuple of (changed_lines_dict mapping line numbers to content, line_numbers list)
        """
        changed_lines_dict = {}
        line_numbers = []
        current_line = 0

        for line in patch.split("\n"):
            if line.startswith("@@"):
                # Parse the @@ line to get the starting line number
                match = re.search(r"\+(\d+)", line)
                if match:
                    current_line = int(match.group(1)) - 1
                continue

            if line.startswith("+") and not line.startswith("+++"):
                current_line += 1
                changed_lines_dict[current_line] = line[1:].strip()
                line_numbers.append(current_line)
            elif not line.startswith("-"):
                current_line += 1

        return changed_lines_dict, line_numbers

    def analyze_code(
        self, filename: str, code: str, changed_lines_dict: Dict[int, str]
    ) -> List[dict]:
        """
        Analyze code using Gemini's API to generate review comments

        Args:
            filename (str): Name of the file being analyzed
            code (str): Full file content
            changed_lines_dict (Dict[int, str]): Dictionary mapping line numbers to changed lines

        Returns:
            List of dictionaries containing review comments and their positions
        """
        try:
            changed_lines_formatted = "\n".join(
                f"Line {line_num}: {content}"
                for line_num, content in changed_lines_dict.items()
            )
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
            
            Changed lines (with line numbers):
            ```
            {changed_lines_formatted}
            ```
            
            Full context:
            ```{file_extension}
            {code}
            ```
            
            Provide each piece of feedback in the following format:
            ISSUE: [Brief description of the issue]
            LINE: [Specific line number where the issue occurs]
            SUGGESTION: [Specific suggestion for improvement]
            ---

            Remember to always include the LINE number from the 'Changed lines' section above.
            """

            response = self.model.generate_content(prompt)
            return self._parse_ai_feedback(
                response.text, list(changed_lines_dict.keys())
            )

        except Exception as e:
            print(f"Error analyzing code: {e}")
            return []

    def _parse_ai_feedback(
        self, feedback_text: str, valid_line_numbers: List[int]
    ) -> List[dict]:
        """
        Parse AI feedback into structured format

        Args:
            feedback_text (str): Raw feedback from Gemini
            valid_line_numbers (List[int]): List of valid line numbers for comments

        Returns:
            List of dictionaries containing parsed feedback with line numbers
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
            elif line.startswith("LINE:"):
                try:
                    # Extract the line number and validate it
                    line_text = line[5:].strip()
                    line_num = int(re.search(r"\d+", line_text).group())
                    if line_num in valid_line_numbers:
                        current_comment["line"] = line_num
                    else:
                        # Default to the first valid line if the suggested line is invalid
                        current_comment["line"] = valid_line_numbers[0]
                except (ValueError, AttributeError):
                    current_comment["line"] = valid_line_numbers[0]
            elif line.startswith("SUGGESTION:"):
                current_comment["body"] = (
                    f"{current_comment.get('body', '')}\n\nSuggestion: {line[11:].strip()}"
                )

        if current_comment.get("body"):
            comments.append(current_comment)

        return [c for c in comments if "line" in c]

    def post_review_comments(
        self, repo_name: str, pr_number: int, filename: str, comments: List[dict]
    ):
        """
        Post review comments on the pull request using the bot identity

        Args:
            repo_name (str): Repository name
            pr_number (int): Pull request number
            filename (str): File being reviewed
            comments (List[dict]): List of review comments with line numbers
        """
        try:
            repo = self.github.get_repo(repo_name)
            pull_request = repo.get_pull(pr_number)
            commit = pull_request.get_commits().reversed[0]

            review_comments = []
            for comment in comments:
                if "line" in comment:
                    review_comments.append(
                        {
                            "path": filename,
                            "line": comment["line"],
                            "body": f"🤖 Code Review Bot:\n\n{comment['body']}",
                        }
                    )

            if review_comments:
                pull_request.create_review(
                    commit=commit, comments=review_comments, event="COMMENT"
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
    for filename, content, changed_lines_dict, line_numbers in changes:
        review_comments = bot.analyze_code(filename, content, changed_lines_dict)
        if review_comments:
            bot.post_review_comments(repo_name, pr_number, filename, review_comments)


if __name__ == "__main__":
    main()
