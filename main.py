import os
from dotenv import load_dotenv
from src.github_app_auth import GitHubAppAuth
from src.code_review_bot import CodeReviewBot

load_dotenv()
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
