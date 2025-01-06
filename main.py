import os
import re
import jwt
import time
import requests
from datetime import datetime
from typing import List, Tuple, Optional, Dict
from github import Github, GithubIntegration
import google.generativeai as genai
from github.PullRequest import PullRequest
from github.Repository import Repository
from github.ContentFile import ContentFile


class GitHubAppAuth:
    def __init__(self, app_id: str, private_key: str):
        """
        Initialize GitHub App authentication

        Args:
            app_id (str): GitHub App ID
            private_key (str): GitHub App private key
        """
        self.app_id = app_id
        self.private_key = private_key
        self.jwt_token = None
        self.jwt_expires_at = 0
        self.installation_token = None
        self.token_expires_at = 0

    def _create_jwt(self) -> str:
        """Create a JWT for GitHub App authentication"""
        now = int(time.time())
        if self.jwt_token and now < self.jwt_expires_at - 60:
            return self.jwt_token

        payload = {
            "iat": now,
            "exp": now + 600,  # JWT valid for 10 minutes
            "iss": self.app_id,
        }

        self.jwt_token = jwt.encode(payload, self.private_key, algorithm="RS256")
        self.jwt_expires_at = now + 600
        return self.jwt_token

    def get_installation_token(self, installation_id: str) -> str:
        """
        Get an installation access token

        Args:
            installation_id (str): GitHub App installation ID

        Returns:
            str: Installation access token
        """
        now = int(time.time())
        if self.installation_token and now < self.token_expires_at - 60:
            return self.installation_token

        jwt_token = self._create_jwt()
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        response = requests.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers=headers,
        )
        response.raise_for_status()

        data = response.json()
        self.installation_token = data["token"]

        # Convert the ISO 8601 timestamp to Unix timestamp
        expires_at = datetime.strptime(
            data["expires_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).timestamp()
        self.token_expires_at = int(expires_at)

        return self.installation_token


class CodeReviewBot:
    def __init__(
        self, app_auth: GitHubAppAuth, installation_id: str, gemini_api_key: str
    ):
        """
        Initialize the code review bot with GitHub App authentication

        Args:
            app_auth (GitHubAppAuth): GitHub App authentication handler
            installation_id (str): GitHub App installation ID
            gemini_api_key (str): Gemini API key for code analysis
        """
        self.app_auth = app_auth
        self.installation_id = installation_id
        self.github = self._get_github_client()
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel("gemini-1.5-pro")

    def _get_github_client(self) -> Github:
        """Get a GitHub client with fresh installation token"""
        token = self.app_auth.get_installation_token(self.installation_id)
        return Github(token)

    def _refresh_github_client(self):
        """Refresh GitHub client with a new token if needed"""
        self.github = self._get_github_client()

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
        """
        try:
            self._refresh_github_client()
            repo = self.github.get_repo(repo_name)
            pull_request = repo.get_pull(pr_number)
            files = pull_request.get_files()

            changes = []
            for file in files:
                if file.filename.endswith(
                    (".py", ".js", ".ts", ".java", ".cpp", ".jsx", ".tsx")
                ):
                    patch = file.patch
                    if patch is None:
                        print(
                            f"No patch available for file {file.filename}. Skipping..."
                        )
                        continue

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
        """Extract changed lines and their numbers from a patch"""
        changed_lines_dict = {}
        line_numbers = []
        current_line = 0

        for line in patch.split("\n"):
            if line.startswith("@@"):
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
        """Analyze code using Gemini API"""
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
        """Parse AI feedback into structured format"""
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
                    line_text = line[5:].strip()
                    line_num = int(re.search(r"\d+", line_text).group())
                    if line_num in valid_line_numbers:
                        current_comment["line"] = line_num
                    else:
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
        """Post review comments using GitHub App identity"""
        try:
            self._refresh_github_client()
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
                            "body": f"{comment['body']}\n\n_I am a GitHub App bot providing automated code review suggestions._",
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
    app_id = os.getenv("GITHUB_APP_ID")
    private_key = os.getenv("GITHUB_PRIVATE_KEY")
    installation_id = os.getenv("GITHUB_INSTALLATION_ID")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    repo_name = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("GITHUB_PR_NUMBER")

    # Validate environment variables
    if not all(
        [app_id, private_key, installation_id, gemini_api_key, repo_name, pr_number]
    ):
        raise ValueError("Missing required environment variables")

    try:
        pr_number = int(pr_number)
    except ValueError:
        raise ValueError("GITHUB_PR_NUMBER must be an integer")

    # Initialize GitHub App authentication
    app_auth = GitHubAppAuth(app_id, private_key)

    # Initialize and run the bot
    bot = CodeReviewBot(app_auth, installation_id, gemini_api_key)

    # Get changes from the pull request
    changes = bot.get_pull_request_changes(repo_name, pr_number)

    # Analyze each changed file and post comments
    for filename, content, changed_lines_dict, line_numbers in changes:
        review_comments = bot.analyze_code(filename, content, changed_lines_dict)
        if review_comments:
            bot.post_review_comments(repo_name, pr_number, filename, review_comments)


if __name__ == "__main__":
    main()
