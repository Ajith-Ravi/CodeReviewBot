import os
import re
from typing import List, Tuple, Dict
from github import Github
import google.generativeai as genai
from .github_app_auth import GitHubAppAuth


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
                if not file.filename.endswith((".xml", ".bin")):
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

    @staticmethod
    def _extract_changed_lines(patch: str) -> Tuple[Dict[int, str], List[int]]:
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
            
            Provide colored feedback on the code changes with + and - signs using HTML tags for green and red colors respectively.
            For example:
            <span style="color:green">+ This is an addition</span>
            <span style="color:red">- This is a deletion</span>
            """

            response = self.model.generate_content(prompt)
            return self._parse_ai_feedback(
                response.text, list(changed_lines_dict.keys())
            )

        except Exception as e:
            print(f"Error analyzing code: {e}")
            return []

    @staticmethod
    def _parse_ai_feedback(
        feedback_text: str, valid_line_numbers: List[int]
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
        """Post review comments using GitHub App identity with background-colored suggestions"""
        try:
            self._refresh_github_client()
            repo = self.github.get_repo(repo_name)
            pull_request = repo.get_pull(pr_number)
            commit = pull_request.get_commits().reversed[0]

            review_comments = []
            for comment in comments:
                if "line" in comment:
                    # Create a formatted comment with background-colored suggestions
                    formatted_body = []
                    if "+" in comment.get("body", ""):
                        formatted_body.append("🟢 **Positive Suggestions:**")
                        formatted_body.append(
                            "".join(
                                [
                                    f"`{line}`{' ' if line.startswith('+') else ''}"
                                    for line in comment["body"].split("\n")
                                    if line.startswith("+")
                                ]
                            )
                        )

                    if "-" in comment.get("body", ""):
                        formatted_body.append("🔴 **Potential Issues:**")
                        formatted_body.append(
                            "".join(
                                [
                                    f"`{line}`{' ' if line.startswith('-') else ''}"
                                    for line in comment["body"].split("\n")
                                    if line.startswith("-")
                                ]
                            )
                        )

                    # Add main comment body
                    formatted_body.append("\n" + comment["body"])

                    review_comments.append(
                        {
                            "path": filename,
                            "line": comment["line"],
                            "body": "\n".join(formatted_body),
                        }
                    )

            if review_comments:
                pull_request.create_review(
                    commit=commit, comments=review_comments, event="COMMENT"
                )

        except Exception as e:
            print(f"Error posting review comments: {e}")
