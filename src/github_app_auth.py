import jwt
import time
import requests
from datetime import datetime


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
