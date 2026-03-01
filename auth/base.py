"""
Abstract base for authentication strategies.
Interface Segregation: defines the minimal contract any auth method must fulfill.
"""

from abc import ABC, abstractmethod
from models.auth_result import AuthResult


class AuthStrategy(ABC):
    """Contract for all authentication strategies."""

    @abstractmethod
    def authenticate(self) -> AuthResult:
        """Attempt to authenticate and return the result."""
        ...

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Check if we currently have a valid session."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Clean up resources (browser, session, etc.)."""
        ...
