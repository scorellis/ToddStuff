"""
Selenium-based authentication strategy.
Handles Google OAuth login flow via real browser automation.

This is the primary strategy because:
- Google OAuth requires a real browser (no simple HTTP POST)
- reCAPTCHA requires browser environment
- Cookie-based session can be captured and reused
"""

import json
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

from auth.base import AuthStrategy
from config.settings import AppConfig
from models.auth_result import AuthResult, AuthStatus
from utils.logger import get_logger

logger = get_logger(__name__)


class SeleniumAuthStrategy(AuthStrategy):
    """Authenticate to sipandscript.com via Selenium browser automation."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._driver = None  # Optional[webdriver.Chrome]
        self._authenticated = False

    # ------------------------------------------------------------------ #
    #  Public interface (AuthStrategy contract)
    # ------------------------------------------------------------------ #

    def authenticate(self) -> AuthResult:
        """Full authentication flow: open browser → login → capture session."""
        try:
            self._init_browser()
            logger.info("Browser initialized. Navigating to WordPress login...")

            # Step 1: Navigate to the WP login page
            self._driver.get(self._config.site.wp_login_url)
            time.sleep(2)

            # Step 2: Detect login method available
            login_method = self._detect_login_method()
            logger.info(f"Detected login method: {login_method}")

            # Step 3: Execute the appropriate login flow
            if self._config.auth.manual_mode:
                return self._manual_login_flow()

            if login_method == "google_oauth":
                return self._google_oauth_flow()
            elif login_method == "wp_standard":
                return self._wp_standard_flow()
            else:
                return self._manual_login_flow()

        except WebDriverException as e:
            logger.error(f"Browser error: {e}")
            return AuthResult(
                status=AuthStatus.FAILED_NETWORK,
                message=f"Browser/driver error: {str(e)[:200]}",
            )
        except Exception as e:
            logger.error(f"Unexpected error during auth: {e}")
            return AuthResult(
                status=AuthStatus.FAILED_UNKNOWN,
                message=f"Unexpected error: {str(e)[:200]}",
            )

    def is_authenticated(self) -> bool:
        """Check if current browser session is logged in."""
        if not self._driver or not self._authenticated:
            return False
        try:
            # Navigate to wp-admin; if we're redirected to login, we're not auth'd
            self._driver.get(f"{self._config.site.site_url}/wp-admin/")
            time.sleep(2)
            return "wp-login" not in self._driver.current_url
        except WebDriverException:
            return False

    def close(self) -> None:
        """Quit browser and release resources."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
        self._authenticated = False

    # ------------------------------------------------------------------ #
    #  Private: browser setup
    # ------------------------------------------------------------------ #

    def _init_browser(self) -> None:
        """Set up Chrome with anti-detection options."""
        options = Options()

        if self._config.browser.headless:
            options.add_argument("--headless=new")

        # Anti-bot-detection flags
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=service, options=options)

        # Override navigator.webdriver to avoid detection
        self._driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )

        logger.info("Chrome browser ready.")

    # ------------------------------------------------------------------ #
    #  Private: login method detection
    # ------------------------------------------------------------------ #

    def _detect_login_method(self) -> str:
        """Inspect the login page to determine what auth methods are available."""
        page_source = self._driver.page_source.lower()

        # Look for Google OAuth buttons/links
        google_indicators = [
            "google",
            "oauth",
            "accounts.google.com",
            "gsi/client",
            "login-with-google",
            "wp-social-login",
            "social-login",
        ]
        for indicator in google_indicators:
            if indicator in page_source:
                return "google_oauth"

        # Look for standard WP login form
        try:
            self._driver.find_element(By.ID, "user_login")
            return "wp_standard"
        except NoSuchElementException:
            pass

        return "unknown"

    # ------------------------------------------------------------------ #
    #  Private: Google OAuth flow
    # ------------------------------------------------------------------ #

    def _google_oauth_flow(self) -> AuthResult:
        """Attempt automated Google OAuth sign-in."""
        logger.info("Attempting Google OAuth flow...")

        try:
            # Find and click the Google login button
            google_btn = self._find_google_login_button()
            if not google_btn:
                logger.warning("Could not find Google login button. Falling back to manual.")
                return self._manual_login_flow()

            google_btn.click()
            time.sleep(3)

            # Handle Google sign-in page
            # Switch to Google's window if popup opened
            if len(self._driver.window_handles) > 1:
                self._driver.switch_to.window(self._driver.window_handles[-1])

            # Enter email
            email_input = WebDriverWait(self._driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]'))
            )
            email_input.clear()
            email_input.send_keys(self._config.auth.google_email)

            # Click Next
            next_btn = self._driver.find_element(By.ID, "identifierNext")
            next_btn.click()
            time.sleep(3)

            # Enter password
            password_input = WebDriverWait(self._driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="password"]'))
            )
            password_input.clear()
            password_input.send_keys(self._config.auth.google_password)

            # Click Next
            pw_next_btn = self._driver.find_element(By.ID, "passwordNext")
            pw_next_btn.click()
            time.sleep(5)

            # Check for 2FA or other challenges
            challenge = self._detect_google_challenge()
            if challenge:
                logger.warning(f"Google challenge detected: {challenge}")
                return self._handle_google_challenge(challenge)

            # Switch back to main window if needed
            if len(self._driver.window_handles) > 1:
                self._driver.switch_to.window(self._driver.window_handles[0])

            # Wait for redirect back to sipandscript
            return self._wait_for_authenticated_state()

        except TimeoutException:
            logger.error("Timeout during Google OAuth flow")
            return AuthResult(
                status=AuthStatus.FAILED_UNKNOWN,
                message="Timed out during Google sign-in. Google may have blocked the attempt.",
            )

    def _find_google_login_button(self):
        """Try multiple selectors to find the Google login button."""
        selectors = [
            (By.CSS_SELECTOR, '[class*="google"]'),
            (By.CSS_SELECTOR, '[id*="google"]'),
            (By.CSS_SELECTOR, '[data-provider="google"]'),
            (By.XPATH, '//a[contains(@href, "google")]'),
            (By.XPATH, '//button[contains(., "Google")]'),
            (By.XPATH, '//a[contains(., "Google")]'),
            (By.CSS_SELECTOR, '.wp-social-login-provider-google'),
        ]
        for by, selector in selectors:
            try:
                return self._driver.find_element(by, selector)
            except NoSuchElementException:
                continue
        return None

    def _detect_google_challenge(self):
        """Check if Google is presenting a challenge (2FA, captcha, etc.)."""
        page_source = self._driver.page_source.lower()
        checks = {
            "2-step verification": "2fa",
            "verify it's you": "identity_verification",
            "unusual activity": "bot_detection",
            "captcha": "captcha",
            "recaptcha": "captcha",
            "confirm your recovery": "recovery",
        }
        for text, challenge_type in checks.items():
            if text in page_source:
                return challenge_type
        return None

    def _handle_google_challenge(self, challenge: str) -> AuthResult:
        """Handle various Google authentication challenges."""
        status_map = {
            "2fa": AuthStatus.FAILED_2FA,
            "captcha": AuthStatus.FAILED_CAPTCHA,
            "bot_detection": AuthStatus.FAILED_BOT_DETECTION,
            "identity_verification": AuthStatus.FAILED_BOT_DETECTION,
            "recovery": AuthStatus.FAILED_UNKNOWN,
        }
        status = status_map.get(challenge, AuthStatus.FAILED_UNKNOWN)

        # For challenges, offer manual fallback
        logger.info("Switching to manual mode — please complete the challenge in the browser.")
        print("\n" + "=" * 60)
        print(f"  ⚠️  Google challenge detected: {challenge}")
        print("  Please complete the sign-in in the browser window.")
        print("  Press ENTER here once you've finished logging in.")
        print("=" * 60)

        input()  # Wait for user
        return self._wait_for_authenticated_state()

    # ------------------------------------------------------------------ #
    #  Private: WP standard login (fallback)
    # ------------------------------------------------------------------ #

    def _wp_standard_flow(self) -> AuthResult:
        """Attempt standard WordPress username/password login (unlikely for this site)."""
        logger.info("Attempting standard WordPress login...")
        # This probably won't work for sipandscript since they use Google OAuth,
        # but including it for completeness / future flexibility.
        return AuthResult(
            status=AuthStatus.FAILED_UNKNOWN,
            message="Standard WP login detected but Google credentials won't work here. "
                    "Try --manual mode instead.",
        )

    # ------------------------------------------------------------------ #
    #  Private: manual-assist flow
    # ------------------------------------------------------------------ #

    def _manual_login_flow(self) -> AuthResult:
        """Let the user log in manually, then capture the session."""
        logger.info("Manual login mode activated.")

        print("\n" + "=" * 60)
        print("  🖱️  MANUAL LOGIN MODE")
        print("  " + "-" * 56)
        print(f"  The browser is open at: {self._driver.current_url}")
        print("  Please log in manually via Google.")
        print("  Once you see the WordPress dashboard,")
        print("  come back here and press ENTER.")
        print("=" * 60)

        input()  # Wait for user to complete login
        return self._wait_for_authenticated_state()

    # ------------------------------------------------------------------ #
    #  Private: session verification & cookie capture
    # ------------------------------------------------------------------ #

    def _wait_for_authenticated_state(self) -> AuthResult:
        """Verify we're logged in and capture session cookies."""
        try:
            # Give a moment for redirects to settle
            time.sleep(3)

            current_url = self._driver.current_url
            logger.info(f"Current URL after login: {current_url}")

            # Check if we ended up at wp-admin or similar authenticated page
            self._driver.get(f"{self._config.site.site_url}/wp-admin/")
            time.sleep(3)

            if "wp-login" in self._driver.current_url:
                return AuthResult(
                    status=AuthStatus.FAILED_CREDENTIALS,
                    message="Redirected back to login. Authentication did not succeed.",
                )

            # Success! Capture cookies
            cookies = {c["name"]: c["value"] for c in self._driver.get_cookies()}
            self._save_cookies(cookies)
            self._authenticated = True

            logger.info(f"✅ Authentication successful! Captured {len(cookies)} cookies.")

            return AuthResult(
                status=AuthStatus.SUCCESS,
                message=f"Authenticated successfully. {len(cookies)} cookies saved.",
                cookies=cookies,
            )

        except Exception as e:
            return AuthResult(
                status=AuthStatus.FAILED_UNKNOWN,
                message=f"Error verifying authentication: {str(e)[:200]}",
            )

    def _save_cookies(self, cookies: dict[str, str]) -> None:
        """Persist cookies to disk for reuse across runs."""
        cookie_path = self._config.browser.cookie_file
        with open(cookie_path, "w") as f:
            json.dump(cookies, f, indent=2)
        logger.info(f"Cookies saved to {cookie_path}")

    def load_saved_cookies(self) -> AuthResult:
        """Try to reuse previously saved cookies instead of re-logging in."""
        cookie_path = self._config.browser.cookie_file
        if not cookie_path.exists():
            return AuthResult(
                status=AuthStatus.FAILED_UNKNOWN,
                message="No saved cookies found.",
            )

        try:
            self._init_browser()
            # Must navigate to domain first before setting cookies
            self._driver.get(self._config.site.site_url)
            time.sleep(2)

            with open(cookie_path) as f:
                cookies = json.load(f)

            for name, value in cookies.items():
                self._driver.add_cookie({"name": name, "value": value})

            # Verify the cookies work
            self._driver.get(f"{self._config.site.site_url}/wp-admin/")
            time.sleep(3)

            if "wp-login" not in self._driver.current_url:
                self._authenticated = True
                return AuthResult(
                    status=AuthStatus.SUCCESS,
                    message="Authenticated via saved cookies.",
                    cookies=cookies,
                )
            else:
                return AuthResult(
                    status=AuthStatus.FAILED_CREDENTIALS,
                    message="Saved cookies expired. Need to re-authenticate.",
                )

        except Exception as e:
            return AuthResult(
                status=AuthStatus.FAILED_UNKNOWN,
                message=f"Error loading cookies: {str(e)[:200]}",
            )
