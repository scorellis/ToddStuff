"""
Unit tests for data models: EventData, Venue, Organizer, AuthResult.
"""

import pytest
from models.event import EventData, Venue, Organizer
from models.auth_result import AuthResult, AuthStatus
from tests.conftest import make_event, make_auth_result


# =========================================================================== #
#  EventData validation
# =========================================================================== #

class TestEventDataValidation:
    """EventData.validate() should catch missing required fields."""

    def test_valid_event_has_no_errors(self):
        event = make_event()
        assert event.validate() == []

    def test_missing_title(self):
        event = make_event(title="")
        errors = event.validate()
        assert len(errors) == 1
        assert "title" in errors[0].lower()

    def test_missing_description(self):
        event = make_event(description="")
        errors = event.validate()
        assert len(errors) == 1
        assert "description" in errors[0].lower()

    def test_missing_start_date(self):
        event = make_event(start_date="")
        errors = event.validate()
        assert any("start date" in e.lower() for e in errors)

    def test_missing_start_time(self):
        event = make_event(start_time="")
        errors = event.validate()
        assert any("start time" in e.lower() for e in errors)

    def test_missing_end_date(self):
        event = make_event(end_date="")
        errors = event.validate()
        assert any("end date" in e.lower() for e in errors)

    def test_missing_end_time(self):
        event = make_event(end_time="")
        errors = event.validate()
        assert any("end time" in e.lower() for e in errors)

    def test_all_fields_missing_returns_six_errors(self):
        event = EventData()  # all defaults are empty
        errors = event.validate()
        assert len(errors) == 6

    def test_optional_fields_dont_cause_errors(self):
        """Fields like event_url, capacity, custom_state are optional."""
        event = make_event(event_url="", ticket_max_capacity="", custom_state="", custom_city="")
        assert event.validate() == []


# =========================================================================== #
#  EventData defaults
# =========================================================================== #

class TestEventDataDefaults:

    def test_default_timezone(self):
        event = EventData()
        assert event.timezone == "America/New_York"

    def test_default_all_day_is_false(self):
        event = EventData()
        assert event.all_day is False

    def test_default_venue_is_empty(self):
        event = EventData()
        assert event.venue.venue_id is None
        assert event.venue.name == ""

    def test_default_organizer_is_empty(self):
        event = EventData()
        assert event.organizer.organizer_id is None
        assert event.organizer.name == ""


# =========================================================================== #
#  Venue
# =========================================================================== #

class TestVenue:

    def test_venue_with_id_only(self):
        v = Venue(venue_id=518716)
        assert v.venue_id == 518716
        assert v.name == ""

    def test_venue_with_full_details(self):
        v = Venue(
            name="Aged in Oak",
            address="123 Main St",
            city="Boston",
            state="MA",
            zip_code="02116",
            country="United States",
        )
        assert v.venue_id is None
        assert v.city == "Boston"

    def test_venue_default_country(self):
        v = Venue()
        assert v.country == "United States"


# =========================================================================== #
#  Organizer
# =========================================================================== #

class TestOrganizer:

    def test_organizer_with_id_only(self):
        o = Organizer(organizer_id=12345)
        assert o.organizer_id == 12345

    def test_organizer_with_details(self):
        o = Organizer(name="Jane Doe", email="jane@example.com", phone="555-1234")
        assert o.name == "Jane Doe"
        assert o.email == "jane@example.com"


# =========================================================================== #
#  AuthResult
# =========================================================================== #

class TestAuthResult:

    def test_success_result(self):
        result = make_auth_result(success=True)
        assert result.is_success is True
        assert result.needs_manual_intervention is False

    def test_failed_result(self):
        result = make_auth_result(success=False)
        assert result.is_success is False

    def test_captcha_needs_manual(self):
        result = AuthResult(
            status=AuthStatus.FAILED_CAPTCHA,
            message="reCAPTCHA detected",
        )
        assert result.needs_manual_intervention is True

    def test_2fa_needs_manual(self):
        result = AuthResult(
            status=AuthStatus.FAILED_2FA,
            message="2FA required",
        )
        assert result.needs_manual_intervention is True

    def test_bot_detection_needs_manual(self):
        result = AuthResult(
            status=AuthStatus.FAILED_BOT_DETECTION,
            message="Bot detected",
        )
        assert result.needs_manual_intervention is True

    def test_manual_required_needs_manual(self):
        result = AuthResult(
            status=AuthStatus.MANUAL_REQUIRED,
            message="Manual login needed",
        )
        assert result.needs_manual_intervention is True

    def test_network_failure_does_not_need_manual(self):
        result = AuthResult(
            status=AuthStatus.FAILED_NETWORK,
            message="Connection refused",
        )
        assert result.needs_manual_intervention is False

    def test_cookies_default_to_empty(self):
        result = AuthResult(status=AuthStatus.SUCCESS, message="ok")
        assert result.cookies == {}
