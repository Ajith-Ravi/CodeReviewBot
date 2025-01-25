# Code Review Bot

This project is a GitHub App that performs automated code reviews on pull requests. It uses the GitHub API for authentication and interaction with repositories, and the Gemini API for code analysis.

## Features

- Automatically reviews code changes in pull requests.
- Provides actionable feedback on code quality, potential bugs, performance improvements, and more.
- Supports multiple programming languages including Python, JavaScript, TypeScript, Java, C++, JSX, and TSX.

## Installation

### Prerequisites

- Python 3.13
- pip (Python package installer)
- GitHub App credentials (App ID, Private Key, Installation ID)
- Gemini API key

### Setup

1. **Clone the repository:**

   ```sh
   git clone https://github.com/{your-username}/code-review-bot.git
   ```

2. **Create a Virtual Environment and Install dependencies:**

   ```sh
   python3 -m venv bot-venv
   source bot-venv/bin/activate
   python3 -m pip install --upgrade pip
   pip3 install -r dependencies/requirements.txt
   ```

3. **Set up environment variables:**

   Create a `.env` file in the root directory and add the following variables:

   ```env
   GITHUB_APP_ID=your_github_app_id
   GITHUB_PRIVATE_KEY=your_github_private_key
   GITHUB_INSTALLATION_ID=your_github_installation_id
   GEMINI_API_KEY=your_gemini_api_key
   ```

### GitHub Actions Workflow

The project includes a GitHub Actions workflow (`.github/workflows/code-review.yaml`) to automate the code review process on pull requests.

1. **Create GitHub Secrets:**

   In your GitHub repository, go to `Settings` > `Secrets` and add the following secrets:

   - `GH_TOKEN`
   - `GEMINI_API_KEY`
   - `GH_APP_ID`
   - `GH_PRIVATE_KEY`
   - `GH_INSTALLATION_ID`

2. **Configure the workflow:**

   The workflow is triggered on pull request events (`opened` and `synchronize`). It sets up Python, installs dependencies, and runs the code review bot.


## Usage

### Running the Bot Locally

1. **Run the bot:**

   ```sh
   python3 main.py
   ```

   The bot will authenticate using the GitHub App credentials, fetch the changes from the pull request, analyze the code using the Gemini API, and post review comments.

### Code Structure

- `main.py`: Entry point of the application. Loads environment variables, initializes the bot, and runs the code review process.
- `src/github_app_auth.py`: Handles GitHub App authentication and token management.
- `src/code_review_bot.py`: Contains the main logic for fetching pull request changes, analyzing code, and posting review comments.

## Contributing

1. Fork the repository.
2. Create a new branch (`git checkout -b feature-branch`).
3. Make your changes.
4. Commit your changes (`git commit -am 'Add new feature'`).
5. Push to the branch (`git push origin feature-branch`).
6. Create a new Pull Request.


## Contact

For any questions or issues, please open an issue on GitHub or contact the repository owner.

---

This README provides a comprehensive guide to setting up, configuring, and using the Code Review Bot. It includes installation instructions, usage details, and information on the project's structure and contributing guidelines.