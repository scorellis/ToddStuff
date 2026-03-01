"""
Integration tests — full submit flow against a local mock server.

This spins up a tiny HTTP server that mimics sipandscript.com's
Community Events form behavior:
  - GET /allevents/squad/add  → returns form HTML with nonces
  - POST /allevents/squad/add → validates and returns success/error

No real network calls, no real browser, no Selenium.
Run with: pytest tests/test_integration.py -v
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
from pathlib import Path

import pytest

from core.submitter import EventSubmitter, FORM_URL
from core.csv_parser import parse_csv
from models.event import EventData, Venue
from tests.conftest import make_event, FAKE_FORM_HTML, FAKE_ERROR_HTML


# =========================================================================== #
#  Mock WordPress Server
# =========================================================================== #

class MockWordPressHandler(BaseHTTPRequestHandler):
    """
    Fake server mimicking The Events Calendar Community Events endpoints.

    Behavior:
      GET  /allevents/squad/add → 200 + form HTML with nonces
      POST /allevents/squad/add → validates post_title + _wpnonce
           success → 302 redirect to /allevents/squad/list/
           error   → 200 + error HTML
      GET  /allevents/squad/list/ → 200 (success page)
      GET  /wp-login.php         → 200 (login page — means session expired)
    """

    # Class-level config — tests can toggle these
    require_auth = True
    valid_cookie = "test_session_cookie"
    force_error = False

    def do_GET(self):
        # Check auth
        if self.require_auth and not self._is_authenticated():
            self.send_response(302)
            self.send_header("Location", "/wp-login.php?redirect_to=/allevents/squad/add")
            self.end_headers()
            return

        if self.path.startswith("/allevents/squad/add"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(FAKE_FORM_HTML.encode())

        elif self.path.startswith("/allevents/squad/list"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Your events list</body></html>")

        elif self.path.startswith("/wp-login"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>wp-login page</body></html>")

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if not self._is_authenticated():
            self.send_response(302)
            self.send_header("Location", "/wp-login.php")
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()
        params = parse_qs(body)

        # Validate
        title = params.get("post_title", [""])[0]
        nonce = params.get("_wpnonce", [""])[0]

        if self.force_error or not title or not nonce:
            # Return error page
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(FAKE_ERROR_HTML.encode())
            return

        # Success — redirect to list page
        self.send_response(302)
        self.send_header("Location", "/allevents/squad/list/")
        self.end_headers()

    def _is_authenticated(self) -> bool:
        cookie_header = self.headers.get("Cookie", "")
        return self.valid_cookie in cookie_header

    def log_message(self, format, *args):
        """Suppress server output during tests."""
        pass


@pytest.fixture(scope="module")
def mock_server():
    """Start a mock server on a random port, yield its base URL, then shut down."""
    server = HTTPServer(("127.0.0.1", 0), MockWordPressHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
def submitter(mock_server):
    """Create an EventSubmitter pointed at the mock server with valid cookies."""
    import core.submitter as submitter_module

    # Monkey-patch the FORM_URL to point at our mock server
    original_url = submitter_module.FORM_URL
    submitter_module.FORM_URL = f"{mock_server}/allevents/squad/add"

    s = EventSubmitter(
        cookies={"session": MockWordPressHandler.valid_cookie},
        delay_seconds=0,
    )
    # Also set the cookie without domain restriction for localhost
    s._session.cookies.clear()
    s._session.cookies.set("session", MockWordPressHandler.valid_cookie)

    yield s

    # Restore
    submitter_module.FORM_URL = original_url


@pytest.fixture
def submitter_no_auth(mock_server):
    """Create an EventSubmitter with NO valid cookies (should fail auth)."""
    import core.submitter as submitter_module

    original_url = submitter_module.FORM_URL
    submitter_module.FORM_URL = f"{mock_server}/allevents/squad/add"

    s = EventSubmitter(cookies={"session": "invalid_cookie"}, delay_seconds=0)
    s._session.cookies.clear()
    s._session.cookies.set("session", "invalid_cookie")

    yield s

    submitter_module.FORM_URL = original_url


# =========================================================================== #
#  Integration: full submit flow
# =========================================================================== #

class TestIntegrationSubmit:

    def test_successful_single_event_submit(self, submitter):
        """Full flow: fetch nonces → build form → POST → get redirect to list."""
        event = make_event()
        result = submitter.submit(event)
        assert result.success is True
        assert result.http_status == 200
        assert "list" in result.message.lower() or "submitted" in result.message.lower()

    def test_submit_fails_without_auth(self, submitter_no_auth):
        """Without valid cookies, nonce fetch should fail (redirect to wp-login)."""
        event = make_event()
        result = submitter_no_auth.submit(event)
        assert result.success is False
        assert "expired" in result.message.lower() or "nonce" in result.message.lower()

    def test_submit_fails_with_missing_title(self, submitter):
        """Server rejects events with empty title."""
        event = make_event(title="")
        result = submitter.submit(event)
        # The mock server will reject because title is empty
        assert result.success is False

    def test_batch_submit_multiple_events(self, submitter):
        """Submit 3 events in a batch, all should succeed."""
        events = [
            make_event(title="Event A"),
            make_event(title="Event B"),
            make_event(title="Event C"),
        ]
        results = submitter.submit_batch(events)
        assert len(results) == 3
        assert all(r.success for r in results)


# =========================================================================== #
#  Integration: CSV → submit flow
# =========================================================================== #

class TestIntegrationCsvToSubmit:

    def test_csv_to_submit_end_to_end(self, submitter, tmp_path):
        """Parse a CSV file, then submit all events through the mock server."""
        csv_content = (
            'title,description,start_date,start_time,end_date,end_time,state,city,venue_id\n'
            '"Calligraphy 101","Learn basics","04/15/2026","18:30:00","04/15/2026","20:30:00","MA","Boston",518716\n'
            '"Brush Lettering","Advanced tips","04/22/2026","19:00:00","04/22/2026","21:00:00","NY","Brooklyn",\n'
        )
        csv_file = tmp_path / "integration_test.csv"
        csv_file.write_text(csv_content)

        events = parse_csv(csv_file)
        assert len(events) == 2

        results = submitter.submit_batch(events)
        assert len(results) == 2
        assert all(r.success for r in results)


# =========================================================================== #
#  Integration: nonce extraction from live-ish HTML
# =========================================================================== #

class TestIntegrationNonceFetch:

    def test_fetches_real_nonces_from_mock(self, submitter):
        """GET the mock form page and verify nonces are extracted."""
        nonces = submitter._fetch_nonces()
        assert nonces.post_id == "524553"
        assert nonces.wpnonce == "d0a24d3d3c"
        assert nonces.virtual_nonce == "79362addae"
        assert nonces.status_nonce == "a06c4bb579"
        assert nonces.tickets_nonce == "56436247f1"
