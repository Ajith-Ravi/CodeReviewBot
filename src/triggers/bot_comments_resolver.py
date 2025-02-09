import os
import requests
from src.github_app_auth import GitHubAppAuth
from github import Github
from dotenv import load_dotenv
import logging

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def resolve_bot_comments():
    """
    Resolve conversation threads for bot comments
    """
    # Load environment variables
    app_id = os.getenv("GITHUB_APP_ID")
    private_key = os.getenv("GITHUB_PRIVATE_KEY")
    installation_id = os.getenv("GITHUB_INSTALLATION_ID")
    bot_name = os.getenv("GITHUB_BOT_NAME", "Code Review BoTT")  # Add this as fallback

    # Initialize GitHub App authentication
    app_auth = GitHubAppAuth(app_id, private_key)
    token = app_auth.get_installation_token(installation_id)
    if not token:
        raise ValueError("Failed to obtain installation token")

    github = Github(token)
    repo_name = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("GITHUB_PR_NUMBER")

    try:
        pr_number = int(pr_number)
    except ValueError:
        raise ValueError("GITHUB_PR_NUMBER must be an integer")

    try:
        repo = github.get_repo(repo_name)
        pull_request = repo.get_pull(pr_number)

        logger.info(f"Processing PR {pr_number} in repo {repo_name}")

        comments_url = (
            f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}/comments"
        )
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        response = requests.get(comments_url, headers=headers)
        response.raise_for_status()
        comments = response.json()

        # Resolve bot comments
        resolved_count = 0
        for comment in comments:
            # Check if the comment is from our bot using the bot name
            if (
                comment["user"]["type"] == "Bot"
                and comment["user"]["login"] == bot_name
                and "*This comment has been resolved.*" not in comment["body"]
            ):
                update_url = f"https://api.github.com/repos/{repo_name}/pulls/comments/{comment['id']}"
                updated_body = comment["body"] + "\n\n*This comment has been resolved.*"
                response = requests.patch(
                    update_url, headers=headers, json={"body": updated_body}
                )
                response.raise_for_status()
                resolved_count += 1

        if resolved_count > 0:
            pull_request.create_review(
                body=f"Resolved {resolved_count} bot comments.", event="APPROVE"
            )

    except requests.exceptions.RequestException as e:
        raise Exception(f"GitHub API error: {e}")
    except Exception as e:
        raise Exception(f"Error resolving bot comments: {e}")


if __name__ == "__main__":
    resolve_bot_comments()
