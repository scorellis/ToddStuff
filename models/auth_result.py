"""
Data models for authentication results.
Open/Closed: extend with new fields, don't modify existing ones.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class AuthStatus(Enum):
    SUCCESS = auto()
    FAILED_CREDENTIALS = auto()
    FAILED_CAPTCHA = auto()
    FAILED_2FA = auto()
    FAILED_BOT_DETECTION = auto()
    FAILED_NETWORK = auto()
    FAILED_UNKNOWN = auto()
    MANUAL_REQUIRED = auto()


@dataclass
class AuthResult:
    """Outcome of an authentication attempt."""
    status: AuthStatus
    message: str
    cookies: dict[str, str] = field(default_factory=dict)
    session_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == AuthStatus.SUCCESS

    @property
    def needs_manual_intervention(self) -> bool:
        return self.status in (
            AuthStatus.FAILED_CAPTCHA,
            AuthStatus.FAILED_2FA,
            AuthStatus.FAILED_BOT_DETECTION,
            AuthStatus.MANUAL_REQUIRED,
        )
