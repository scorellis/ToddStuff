"""
Unit tests for the Authenticator (core orchestrator).
Tests the strategy pattern and delegation logic — no real browser involved.
"""

import pytest
from unittest.mock import MagicMock

from core.authenticator import Authenticator
from auth.base import AuthStrategy
from models.auth_result import AuthResult, AuthStatus
from tests.conftest import make_auth_result


class FakeAuthStrategy(AuthStrategy):
    """Controllable fake for testing Authenticator without a real browser."""

    def __init__(self, result=None):
        self._result = result or make_auth_result()
        self._authenticated = False
        self.close_called = False

    def authenticate(self) -> AuthResult:
        if self._result.is_success:
            self._authenticated = True
        return self._result

    def is_authenticated(self) -> bool:
        return self._authenticated

    def close(self) -> None:
        self.close_called = True
        self._authenticated = False


class TestAuthenticator:

    def test_login_returns_success(self):
        strategy = FakeAuthStrategy(make_auth_result(success=True))
        auth = Authenticator(strategy)
        result = auth.login()
        assert result.is_success is True

    def test_login_returns_failure(self):
        strategy = FakeAuthStrategy(make_auth_result(success=False))
        auth = Authenticator(strategy)
        result = auth.login()
        assert result.is_success is False

    def test_check_session_after_success(self):
        strategy = FakeAuthStrategy(make_auth_result(success=True))
        auth = Authenticator(strategy)
        auth.login()
        assert auth.check_session() is True

    def test_check_session_without_login(self):
        strategy = FakeAuthStrategy(make_auth_result(success=True))
        auth = Authenticator(strategy)
        # Don't call login()
        assert auth.check_session() is False

    def test_cleanup_calls_close(self):
        strategy = FakeAuthStrategy()
        auth = Authenticator(strategy)
        auth.cleanup()
        assert strategy.close_called is True

    def test_swap_strategy(self):
        strategy1 = FakeAuthStrategy(make_auth_result(success=False))
        strategy2 = FakeAuthStrategy(make_auth_result(success=True))

        auth = Authenticator(strategy1)
        result1 = auth.login()
        assert result1.is_success is False

        auth.strategy = strategy2  # swap
        assert strategy1.close_called is True  # old strategy cleaned up

        result2 = auth.login()
        assert result2.is_success is True

    def test_login_with_manual_required_result(self):
        result = AuthResult(
            status=AuthStatus.MANUAL_REQUIRED,
            message="Please log in manually.",
        )
        strategy = FakeAuthStrategy(result)
        auth = Authenticator(strategy)
        login_result = auth.login()
        assert login_result.needs_manual_intervention is True
