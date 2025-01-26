import os

import requests

from src.github_app_auth import GitHubAppAuth
from github import Github
from dotenv import load_dotenv

load_dotenv()


def resolve_bot_comments():
    """
    Resolve conversation threads for bot comments
    """
    # Load environment variables
    app_id = os.getenv("GITHUB_APP_ID")
    private_key = os.getenv("GITHUB_PRIVATE_KEY")
    installation_id = os.getenv("GITHUB_INSTALLATION_ID")

    # Initialize GitHub App authentication
    app_auth = GitHubAppAuth(app_id, private_key)
    token = app_auth.get_installation_token(installation_id)
    github = Github(token)

    repo_name = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("GITHUB_PR_NUMBER")

    try:
        repo = github.get_repo(repo_name)
        pull_request = repo.get_pull(pr_number)

        comments_url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}/comments"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        response = requests.get(comments_url, headers=headers)
        comments = response.json()

        # Resolve bot comments
        for comment in comments:
            if comment['user']['login'] == github.get_user().login:
                resolve_url = f"https://api.github.com/repos/{repo_name}/pulls/comments/{comment['id']}/resolve"
                requests.post(resolve_url, headers=headers)

        pull_request.create_review(
            body="All bot comments resolved.", event="APPROVE"
        )
    except Exception as e:
        print(f"Error resolving bot comments: {e}")

if __name__ == "__main__":
    resolve_bot_comments()