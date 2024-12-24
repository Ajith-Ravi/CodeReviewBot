import os
import re
from typing import List, Tuple

import openai
from github import Github

class CodeReviewBot:
    def __init__(self, github_token: str, openai_api_key: str):
        """
        Initialize the code review bot with necessary credentials
        
        Args:
            github_token (str): GitHub personal access token
            openai_api_key (str): OpenAI API key for code analysis
        """
        self.github = Github(github_token)
        openai.api_key = openai_api_key
        
    def get_pull_request_changes(self, repo_name: str, pr_number: int) -> List[Tuple[str, str, List[str]]]:
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
            if file.filename.endswith(('.py', '.js', '.ts', '.java', '.cpp', '.jsx', '.tsx')):
                patch = file.patch
                changed_lines = self._extract_changed_lines(patch)
                content = repo.get_contents(file.filename, ref=pull_request.head.sha).decoded_content.decode()
                changes.append((file.filename, content, changed_lines))
                
        return changes
    
    def _extract_changed_lines(self, patch: str) -> List[str]:
        """Extract the actual changed lines from a patch"""
        changed_lines = []
        for line in patch.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                changed_lines.append(line[1:].strip())
        return changed_lines
    
    def analyze_code(self, code: str, changed_lines: List[str]) -> List[dict]:
        """
        Analyze code using OpenAI's API to generate review comments
        
        Returns:
            List of dictionaries containing review comments and their positions
        """

        changed_lines_combined =   '\n'.join(changed_lines)

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
        
        response = openai.Completion.create(
            engine="gpt-4",
            prompt=prompt,
            max_tokens=1000,
            temperature=0.7
        )
        
        # Parse the response and generate structured feedback
        feedback = self._parse_ai_feedback(response.choices[0].text)
        return feedback
    
    def _parse_ai_feedback(self, feedback_text: str) -> List[dict]:
        """Parse AI feedback into structured format"""
        # Simple parsing logic - can be enhanced based on AI response format
        comments = []
        for line in feedback_text.split('\n'):
            if line.strip():
                comments.append({
                    'body': line.strip(),
                    'position': None  # You might want to implement position detection
                })
        return comments
    
    def post_review_comments(self, repo_name: str, pr_number: int, comments: List[dict]):
        """Post review comments on the pull request"""
        repo = self.github.get_repo(repo_name)
        pull_request = repo.get_pull(pr_number)
        
        for comment in comments:
            pull_request.create_review_comment(
                body=comment['body'],
                commit_id=pull_request.head.sha,
                path=comment.get('path', ''),
                position=comment.get('position', 0)
            )

def main():
    # Load environment variables
    github_token = os.getenv('GITHUB_TOKEN')
    openai_api_key = os.getenv('OPENAI_API_KEY')
    repo_name = os.getenv('GITHUB_REPOSITORY')
    pr_number = int(os.getenv('GITHUB_PR_NUMBER'))
    
    if not all([github_token, openai_api_key, repo_name, pr_number]):
        raise ValueError("Missing required environment variables")
    
    # Initialize and run the bot
    bot = CodeReviewBot(github_token, openai_api_key)
    
    # Get changes from the pull request
    changes = bot.get_pull_request_changes(repo_name, pr_number)
    
    # Analyze each changed file and post comments
    for filename, content, changed_lines in changes:
        review_comments = bot.analyze_code(content, changed_lines)
        bot.post_review_comments(repo_name, pr_number, review_comments)

if __name__ == "__main__":
    main()