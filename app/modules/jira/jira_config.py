"""
jira_integration/jira_config.py
────────────────────────────────
Central configuration for Jira integration.

Usage anywhere in project:
    from jira_integration.jira_config import config
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth


# Load environment variables
# Use absolute path so .env is found regardless of cwd.
# jira_config.py lives at: jira_integration/jira_config.py
# .env lives at:           backend/.env
_THIS_FILE = os.path.abspath(__file__)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE)))
_ENV_PATH = os.path.join(_BACKEND_DIR, ".env")
load_dotenv(dotenv_path=_ENV_PATH, override=True)


@dataclass(frozen=True)
class JiraConfig:
    # ─────────────────────────────
    # Core Jira Credentials
    # ─────────────────────────────
    url: str = field(default_factory=lambda: os.getenv("JIRA_URL", "").strip())
    email: str = field(default_factory=lambda: os.getenv("JIRA_EMAIL", "").strip())
    api_token: str = field(default_factory=lambda: os.getenv("JIRA_API_TOKEN", "").strip())

    # ─────────────────────────────
    # Jira Issue Settings
    # ─────────────────────────────
    project_key: str = field(default_factory=lambda: os.getenv("JIRA_PROJECT_KEY", "").strip())
    issue_type: str = field(default_factory=lambda: os.getenv("JIRA_ISSUE_TYPE", "Bug"))
    assignee_id: str = field(default_factory=lambda: os.getenv("JIRA_ASSIGNEE_ACCOUNT_ID", ""))
    priority: str = field(default_factory=lambda: os.getenv("JIRA_PRIORITY", "High"))

    # ─────────────────────────────
    # Feature Flags
    # ─────────────────────────────
    enabled: bool = field(default_factory=lambda: os.getenv("JIRA_ENABLED", "true").lower() == "true")
    dedup_enabled: bool = field(default_factory=lambda: os.getenv("JIRA_DEDUP_ENABLED", "true").lower() == "true")

    # Labels for created issues
    labels: list = field(default_factory=lambda: ["automation", "regression", "auto-created"])

    # ─────────────────────────────
    # Authentication Helper
    # ─────────────────────────────
    @property
    def auth(self):
        """Return HTTPBasicAuth for Jira requests."""
        return HTTPBasicAuth(self.email, self.api_token)

    # ─────────────────────────────
    # Headers
    # ─────────────────────────────
    @property
    def json_headers(self):
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @property
    def attachment_headers(self):
        return {
            "X-Atlassian-Token": "no-check"
        }

    # ─────────────────────────────
    # Validation
    # ─────────────────────────────
    @property
    def is_valid(self) -> bool:
        """Check required config values."""
        return all([self.url, self.email, self.api_token, self.project_key])

    def validate(self) -> bool:
        """Print helpful message if config missing."""
        if not self.enabled:
            print("[JiraConfig] Jira integration disabled.")
            return False

        missing = [
            name for name, val in {
                "JIRA_URL": self.url,
                "JIRA_EMAIL": self.email,
                "JIRA_API_TOKEN": self.api_token,
                "JIRA_PROJECT_KEY": self.project_key,
            }.items() if not val
        ]

        if missing:
            print(f"[JiraConfig] ⚠️ Missing environment variables: {', '.join(missing)}")
            print("[JiraConfig] Copy `.env.example` → `.env` and fill values.")
            return False

        return True

    # ─────────────────────────────
    # Jira REST Endpoints
    # ─────────────────────────────
    @property
    def issues_endpoint(self) -> str:
        return f"{self.url}/rest/api/3/issue"

    @property
    def search_endpoint(self) -> str:
        return f"{self.url}/rest/api/3/search"

    def attachment_endpoint(self, issue_key: str) -> str:
        return f"{self.url}/rest/api/3/issue/{issue_key}/attachments"

    def comment_endpoint(self, issue_key: str) -> str:
        return f"{self.url}/rest/api/3/issue/{issue_key}/comment"

    def transitions_endpoint(self, issue_key: str) -> str:
        return f"{self.url}/rest/api/3/issue/{issue_key}/transitions"

    def browse_url(self, issue_key: str) -> str:
        return f"{self.url}/browse/{issue_key}"


# ─────────────────────────────
# Singleton instance
# ─────────────────────────────
config = JiraConfig()