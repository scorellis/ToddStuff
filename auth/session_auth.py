"""
HTTP Session-based authentication (fallback strategy).

This is unlikely to work for sipandscript.com because:
- Google OAuth requires browser interaction
- reCAPTCHA blocks automated HTTP requests

Included for SOLID compliance (Open/Closed principle) so we can
swap strategies without modifying the core orchestrator.
"""

import json
import requests

from auth.base import AuthStrategy
from config.settings import AppConfig
from models.auth_result import AuthResult, AuthStatus
from utils.logger import get_logger

logger = get_logger(__name__)


class SessionAuthStrategy(AuthStrategy):
    """Attempt direct HTTP-based authentication (not recommended for OAuth sites)."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._session = requests.Session()
        self._authenticated = False

    def authenticate(self) -> AuthResult:
        """Try to authenticate via HTTP requests."""
        logger.warning(
            "HTTP session auth is unlikely to work with Google OAuth + reCAPTCHA. "
            "Use SeleniumAuthStrategy instead."
        )

        try:
            # Step 1: Hit the login page to get initial cookies/nonces
            resp = self._session.get(self._config.site.wp_login_url, timeout=15)

            if resp.status_code != 200:
                return AuthResult(
                    status=AuthStatus.FAILED_NETWORK,
                    message=f"Login page returned HTTP {resp.status_code}",
                )

            # Step 2: Check if there's a standard WP login form
            if 'name="log"' in resp.text and 'name="pwd"' in resp.text:
                return self._try_wp_login(resp.text)

            # Most likely scenario: OAuth-only login
            return AuthResult(
                status=AuthStatus.MANUAL_REQUIRED,
                message="Login page uses Google OAuth. HTTP-based login is not possible. "
                        "Please use Selenium strategy or --manual mode.",
            )

        except requests.RequestException as e:
            return AuthResult(
                status=AuthStatus.FAILED_NETWORK,
                message=f"Network error: {str(e)[:200]}",
            )

    def _try_wp_login(self, page_html: str) -> AuthResult:
        """Attempt a standard WP form POST (won't work if OAuth-only)."""
        # This is a stub — would need proper nonce extraction for a real WP login
        return AuthResult(
            status=AuthStatus.FAILED_UNKNOWN,
            message="Standard WP login form found but Google credentials required. "
                    "Use Selenium strategy.",
        )

    def is_authenticated(self) -> bool:
        """Check if session cookies grant access."""
        if not self._authenticated:
            return False
        try:
            resp = self._session.get(
                f"{self._config.site.site_url}/wp-admin/",
                allow_redirects=False,
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def close(self) -> None:
        """Close HTTP session."""
        self._session.close()
        self._authenticated = False

    def load_cookies_from_file(self, cookie_file: str) -> None:
        """Load cookies captured by Selenium for HTTP reuse."""
        with open(cookie_file) as f:
            cookies = json.load(f)
        for name, value in cookies.items():
            self._session.cookies.set(name, value)
        logger.info(f"Loaded {len(cookies)} cookies into HTTP session.")
