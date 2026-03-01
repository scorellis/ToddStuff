"""
Core Authenticator — orchestrates the login flow.
Dependency Inversion: depends on AuthStrategy (abstract), not concrete implementations.
"""

from auth.base import AuthStrategy
from models.auth_result import AuthResult, AuthStatus
from utils.logger import get_logger

logger = get_logger(__name__)


class Authenticator:
    """
    Orchestrates authentication using a pluggable strategy.

    Usage:
        strategy = SeleniumAuthStrategy(config)
        auth = Authenticator(strategy)
        result = auth.login()
    """

    def __init__(self, strategy: AuthStrategy) -> None:
        self._strategy = strategy

    @property
    def strategy(self) -> AuthStrategy:
        return self._strategy

    @strategy.setter
    def strategy(self, new_strategy: AuthStrategy) -> None:
        """Swap strategy at runtime (e.g., fallback from Selenium to manual)."""
        self._strategy.close()
        self._strategy = new_strategy

    def login(self) -> AuthResult:
        """Execute the authentication flow and report results."""
        logger.info(f"Starting authentication with {type(self._strategy).__name__}...")

        result = self._strategy.authenticate()

        if result.is_success:
            logger.info(f"✅ {result.message}")
        elif result.needs_manual_intervention:
            logger.warning(f"⚠️  {result.message}")
        else:
            logger.error(f"❌ {result.message}")

        self._print_result_summary(result)
        return result

    def check_session(self) -> bool:
        """Quick check: are we still logged in?"""
        return self._strategy.is_authenticated()

    def cleanup(self) -> None:
        """Release all resources."""
        self._strategy.close()

    @staticmethod
    def _print_result_summary(result: AuthResult) -> None:
        """Pretty-print the auth result for the user."""
        divider = "=" * 60
        print(f"\n{divider}")
        print(f"  AUTH RESULT: {result.status.name}")
        print(f"  {result.message}")

        if result.is_success:
            print(f"  Cookies captured: {len(result.cookies)}")
            wp_cookies = [k for k in result.cookies if k.startswith("wordpress")]
            if wp_cookies:
                print(f"  WordPress cookies: {', '.join(wp_cookies)}")

        if result.needs_manual_intervention:
            print("\n  💡 TIP: Try running with --manual flag:")
            print("     python main.py --manual")

        if not result.is_success and not result.needs_manual_intervention:
            print("\n  💡 NEXT STEPS:")
            print("     1. Try --manual mode: python main.py --manual")
            print("     2. If that fails, contact Sip & Script about API access")

        print(divider)
