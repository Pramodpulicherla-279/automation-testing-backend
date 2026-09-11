"""
test_management/config.py
──────────────────────────
Central configuration for the Test Management MySQL backend.

Usage anywhere in project:
    from app.modules.test_management.config import config
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables.
# Use absolute path so .env is found regardless of cwd.
# config.py lives at: app/modules/test_management/config.py
# .env lives at:      app/.env
_THIS_FILE = os.path.abspath(__file__)
_NEW_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE)))
_ENV_PATH = os.path.join(_NEW_BACKEND_DIR, ".env")
load_dotenv(dotenv_path=_ENV_PATH, override=True)


@dataclass(frozen=True)
class TestManagementConfig:
    mysql_host: str = field(default_factory=lambda: os.getenv("MYSQL_HOST", "localhost"))
    mysql_port: int = field(default_factory=lambda: int(os.getenv("MYSQL_PORT", "3306")))
    mysql_user: str = field(default_factory=lambda: os.getenv("MYSQL_USER", "automation_user"))
    mysql_password: str = field(default_factory=lambda: os.getenv("MYSQL_PASSWORD", "automation_pass"))
    mysql_database: str = field(default_factory=lambda: os.getenv("MYSQL_DATABASE", "automation_testing"))
    db_echo: bool = field(default_factory=lambda: os.getenv("DB_ECHO", "false").lower() == "true")

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )


# ─────────────────────────────
# Singleton instance
# ─────────────────────────────
config = TestManagementConfig()
