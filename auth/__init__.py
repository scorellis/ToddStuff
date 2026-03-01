from .base import AuthStrategy

try:
    from .selenium_auth import SeleniumAuthStrategy
except ImportError:
    SeleniumAuthStrategy = None  # type: ignore

try:
    from .session_auth import SessionAuthStrategy
except ImportError:
    SessionAuthStrategy = None  # type: ignore

__all__ = ["AuthStrategy", "SeleniumAuthStrategy", "SessionAuthStrategy"]
