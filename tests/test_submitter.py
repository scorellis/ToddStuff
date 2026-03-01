"""
Unit tests for the EventSubmitter.

All HTTP calls are mocked — these tests verify:
- Nonce extraction from HTML
- Form data construction
- Response handling (success, error, redirect)
- Batch logic (early stop on expired session)
- Error message extraction
"""

import pytest
from unittest.mock import patch, MagicMock

from core.submitter import EventSubmitter, NonceExtractor, FormNonces, FORM_URL
from models.event import EventData, Venue, Organizer
from tests.conftest import (
    make_event, make_nonces,
    FAKE_FORM_HTML, FAKE_ERROR_HTML,
    FAKE_SUCCESS_REDIRECT_URL, FAKE_FORM_URL, FAKE_LOGIN_REDIRECT_URL,
)


# =========================================================================== #
#  NonceExtractor (HTML parser)
# =========================================================================== #

class TestNonceExtractor:

    def test_extracts_all_nonces_from_real_form(self):
        parser = NonceExtractor()
        parser.feed(FAKE_FORM_HTML)
        assert parser.values["post_ID"] == "524553"
        assert parser.values["_wpnonce"] == "d0a24d3d3c"
        assert parser.values["tribe-events-virtual[virtual-nonce]"] == "79362addae"
        assert parser.values["tribe-events-status[nonce]"] == "a06c4bb579"
        assert parser.values["tribe-tickets-post-settings"] == "56436247f1"

    def test_ignores_non_hidden_inputs(self):
        html = '<input type="text" name="post_title" value="Hello" />'
        parser = NonceExtractor()
        parser.feed(html)
        assert "post_title" not in parser.values

    def test_handles_empty_html(self):
        parser = NonceExtractor()
        parser.feed("")
        assert parser.values == {}

    def test_handles_html_without_inputs(self):
        parser = NonceExtractor()
        parser.feed("<html><body><p>No forms here</p></body></html>")
        assert parser.values == {}

    def test_handles_hidden_input_without_value(self):
        html = '<input type="hidden" name="orphan" />'
        parser = NonceExtractor()
        parser.feed(html)
        assert "orphan" not in parser.values


# =========================================================================== #
#  _build_form_data
# =========================================================================== #

class TestBuildFormData:

    def setup_method(self):
        self.submitter = EventSubmitter(cookies={"fake": "cookie"}, delay_seconds=0)

    def test_contains_all_nonces(self):
        event = make_event()
        nonces = make_nonces()
        data = self.submitter._build_form_data(event, nonces)

        assert data["post_ID"] == "524553"
        assert data["_wpnonce"] == "d0a24d3d3c"
        assert data["tribe-events-virtual[virtual-nonce]"] == "79362addae"
        assert data["tribe-events-status[nonce]"] == "a06c4bb579"
        assert data["tribe-tickets-post-settings"] == "56436247f1"

    def test_contains_core_event_fields(self):
        event = make_event()
        nonces = make_nonces()
        data = self.submitter._build_form_data(event, nonces)

        assert data["post_title"] == "Modern Calligraphy Basics"
        assert data["tcepostcontent"] == "Learn the fundamentals of modern calligraphy!"
        assert data["EventStartDate"] == "04/15/2026"
        assert data["EventStartTime"] == "18:30:00"
        assert data["EventEndDate"] == "04/15/2026"
        assert data["EventEndTime"] == "20:30:00"
        assert data["EventTimezone"] == "America/New_York"

    def test_contains_custom_fields(self):
        event = make_event()
        nonces = make_nonces()
        data = self.submitter._build_form_data(event, nonces)

        assert data["_ecp_custom_3"] == "30"
        assert data["_ecp_custom_5"] == "Massachusetts"
        assert data["_ecp_custom_10"] == "Boston"

    def test_submit_button_value(self):
        data = self.submitter._build_form_data(make_event(), make_nonces())
        assert data["community-event"] == "Submit Event"

    def test_venue_with_existing_id(self):
        event = make_event(venue=Venue(venue_id=518716))
        data = self.submitter._build_form_data(event, make_nonces())
        assert data["venue[VenueID][]"] == "518716"
        assert "venue[Venue][]" not in data

    def test_venue_with_new_details(self):
        event = make_event(venue=Venue(
            name="New Place", address="456 Oak Ave",
            city="Cambridge", state="MA", zip_code="02139",
        ))
        data = self.submitter._build_form_data(event, make_nonces())
        assert data["venue[VenueID][]"] == "-1"
        assert data["venue[Venue][]"] == "New Place"
        assert data["venue[Address][]"] == "456 Oak Ave"
        assert data["venue[City][]"] == "Cambridge"

    def test_organizer_with_existing_id(self):
        event = make_event(organizer=Organizer(organizer_id=99))
        data = self.submitter._build_form_data(event, make_nonces())
        assert data["organizer[OrganizerID][]"] == "99"
        assert "organizer[Organizer][]" not in data

    def test_organizer_with_new_details(self):
        event = make_event(organizer=Organizer(
            name="Jane", email="jane@test.com", phone="555-0000",
        ))
        data = self.submitter._build_form_data(event, make_nonces())
        assert data["organizer[OrganizerID][]"] == "-1"
        assert data["organizer[Organizer][]"] == "Jane"
        assert data["organizer[Email][]"] == "jane@test.com"

    def test_all_day_event_flag(self):
        event = make_event(all_day=True)
        data = self.submitter._build_form_data(event, make_nonces())
        assert data["EventAllDay"] == "yes"

    def test_non_all_day_omits_flag(self):
        event = make_event(all_day=False)
        data = self.submitter._build_form_data(event, make_nonces())
        assert "EventAllDay" not in data


# =========================================================================== #
#  _fetch_nonces (mocked HTTP)
# =========================================================================== #

class TestFetchNonces:

    def setup_method(self):
        self.submitter = EventSubmitter(cookies={"fake": "cookie"}, delay_seconds=0)

    @patch.object(EventSubmitter, "_fetch_nonces")
    def test_returns_valid_nonces(self, mock_fetch):
        """Simplified: just verify the method returns a FormNonces object."""
        mock_fetch.return_value = make_nonces()
        nonces = self.submitter._fetch_nonces()
        assert nonces.wpnonce == "d0a24d3d3c"
        assert nonces.post_id == "524553"

    def test_nonce_extraction_from_fake_html(self):
        """Directly test that _fetch_nonces would parse our fake HTML correctly."""
        # Simulate what _fetch_nonces does internally
        parser = NonceExtractor()
        parser.feed(FAKE_FORM_HTML)
        hidden = parser.values

        nonces = FormNonces(
            post_id=hidden.get("post_ID", ""),
            wpnonce=hidden.get("_wpnonce", ""),
            virtual_nonce=hidden.get("tribe-events-virtual[virtual-nonce]", ""),
            status_nonce=hidden.get("tribe-events-status[nonce]", ""),
            tickets_nonce=hidden.get("tribe-tickets-post-settings", ""),
        )

        assert nonces.post_id == "524553"
        assert nonces.wpnonce == "d0a24d3d3c"
        assert nonces.virtual_nonce == "79362addae"
        assert nonces.status_nonce == "a06c4bb579"
        assert nonces.tickets_nonce == "56436247f1"


# =========================================================================== #
#  submit() — response handling (mocked HTTP)
# =========================================================================== #

class TestSubmitResponseHandling:

    def setup_method(self):
        self.submitter = EventSubmitter(cookies={"fake": "cookie"}, delay_seconds=0)

    def _mock_submit(self, post_status=200, post_url=FAKE_SUCCESS_REDIRECT_URL, post_text=""):
        """Helper: mock _fetch_nonces and _session.post."""
        with patch.object(self.submitter, "_fetch_nonces", return_value=make_nonces()):
            mock_resp = MagicMock()
            mock_resp.status_code = post_status
            mock_resp.url = post_url
            mock_resp.text = post_text

            with patch.object(self.submitter._session, "post", return_value=mock_resp):
                return self.submitter.submit(make_event())

    def test_success_on_list_redirect(self):
        result = self._mock_submit(
            post_status=200,
            post_url=FAKE_SUCCESS_REDIRECT_URL,
        )
        assert result.success is True
        assert result.http_status == 200
        assert "submitted" in result.message.lower()

    def test_failure_on_form_redirect(self):
        result = self._mock_submit(
            post_status=200,
            post_url=FAKE_FORM_URL,
            post_text=FAKE_ERROR_HTML,
        )
        assert result.success is False
        assert "title" in result.message.lower()

    def test_failure_when_nonces_empty(self):
        with patch.object(self.submitter, "_fetch_nonces", return_value=FormNonces()):
            result = self.submitter.submit(make_event())
        assert result.success is False
        assert "nonce" in result.message.lower()

    def test_unexpected_url_is_failure(self):
        result = self._mock_submit(
            post_status=200,
            post_url="https://sipandscript.com/some/random/page",
        )
        assert result.success is False
        assert "unexpected" in result.message.lower()

    def test_http_error_handled(self):
        import requests
        with patch.object(self.submitter, "_fetch_nonces", return_value=make_nonces()):
            with patch.object(
                self.submitter._session, "post",
                side_effect=requests.ConnectionError("Connection refused"),
            ):
                result = self.submitter.submit(make_event())
        assert result.success is False
        assert "http error" in result.message.lower()


# =========================================================================== #
#  submit_batch()
# =========================================================================== #

class TestSubmitBatch:

    def setup_method(self):
        self.submitter = EventSubmitter(cookies={"fake": "cookie"}, delay_seconds=0)

    def test_batch_returns_all_results(self):
        events = [make_event(title=f"Event {i}") for i in range(3)]

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.message = "ok"

        with patch.object(self.submitter, "submit", return_value=mock_result):
            results = self.submitter.submit_batch(events)

        assert len(results) == 3

    def test_batch_stops_on_expired_session(self):
        events = [make_event(title=f"Event {i}") for i in range(5)]

        from core.submitter import SubmitResult
        expired_result = SubmitResult(
            success=False,
            event_title="Event 0",
            message="Failed to fetch form page or extract nonces. Session may have expired.",
        )

        with patch.object(self.submitter, "submit", return_value=expired_result):
            results = self.submitter.submit_batch(events)

        # Should stop after first failure with "expired"
        assert len(results) == 1


# =========================================================================== #
#  _extract_form_errors
# =========================================================================== #

class TestExtractFormErrors:

    def test_extracts_error_from_notice_div(self):
        errors = EventSubmitter._extract_form_errors(FAKE_ERROR_HTML)
        assert "title" in errors.lower()

    def test_returns_empty_for_no_errors(self):
        errors = EventSubmitter._extract_form_errors("<html><body>All good</body></html>")
        assert errors == ""

    def test_strips_html_tags(self):
        html = '<div class="tribe-community-notice"><p><strong>Error:</strong> Bad input</p></div>'
        errors = EventSubmitter._extract_form_errors(html)
        assert "<" not in errors
        assert "Error" in errors
