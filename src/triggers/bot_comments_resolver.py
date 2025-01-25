import os
from src.github_app_auth import GitHubAppAuth
from github import Github


def resolve_bot_comments():
    """
    Handle resolving comments if the resolve command is found
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
    pr_number = int(os.getenv("GITHUB_PR_NUMBER"))

    try:
        repo = github.get_repo(repo_name)
        pull_request = repo.get_pull(pr_number)
        commit = pull_request.get_commits().reversed[0]

        bot_login = github.get_user().login
        comments = pull_request.get_review_comments()
        for comment in comments:
            if comment.user.login == bot_login:
                comment.delete()

        pull_request.create_review(
            commit=commit, body="All bot comments resolved.", event="APPROVE"
        )
    except Exception as e:
        print(f"Error handling resolve comments: {e}")


if __name__ == "__main__":
    resolve_bot_comments()
