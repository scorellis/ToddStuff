"""
Configuration settings loaded from environment variables.
Single Responsibility: All config management lives here.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


@dataclass(frozen=True)
class AuthConfig:
    """Google OAuth credentials and auth-related settings."""
    google_email: str = field(default_factory=lambda: os.getenv("GOOGLE_EMAIL", ""))
    google_password: str = field(default_factory=lambda: os.getenv("GOOGLE_PASSWORD", ""))
    login_timeout: int = field(
        default_factory=lambda: int(os.getenv("LOGIN_TIMEOUT_SECONDS", "60"))
    )
    manual_mode: bool = field(
        default_factory=lambda: os.getenv("MANUAL_MODE", "false").lower() == "true"
    )

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors = []
        if not self.manual_mode:
            if not self.google_email:
                errors.append("GOOGLE_EMAIL is required (or use --manual mode)")
            if not self.google_password:
                errors.append("GOOGLE_PASSWORD is required (or use --manual mode)")
        return errors


@dataclass(frozen=True)
class SiteConfig:
    """Target website URLs."""
    site_url: str = field(
        default_factory=lambda: os.getenv("SITE_URL", "https://sipandscript.com")
    )
    wp_login_url: str = field(
        default_factory=lambda: os.getenv(
            "WP_LOGIN_URL", "https://sipandscript.com/wp-login.php"
        )
    )


@dataclass(frozen=True)
class BrowserConfig:
    """Browser/Selenium settings."""
    headless: bool = field(
        default_factory=lambda: os.getenv("HEADLESS", "false").lower() == "true"
    )
    cookie_file: Path = field(
        default_factory=lambda: _project_root / "session_cookies.json"
    )


@dataclass(frozen=True)
class AppConfig:
    """Top-level config aggregator."""
    auth: AuthConfig = field(default_factory=AuthConfig)
    site: SiteConfig = field(default_factory=SiteConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
