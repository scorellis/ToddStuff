#!/usr/bin/env python3
"""
Standalone test runner — uses only unittest (stdlib).
Run this if you don't have pytest installed yet.

Usage:
    python run_tests.py           # run all tests
    python run_tests.py --unit    # unit tests only (no HTTP)
    python run_tests.py --integ   # integration tests only (mock server)
"""

import sys
import os
import unittest
import argparse
import tempfile
import textwrap
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
from unittest.mock import patch, MagicMock

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.event import EventData, Venue, Organizer
from models.auth_result import AuthResult, AuthStatus
from core.submitter import EventSubmitter, NonceExtractor, FormNonces


# =========================================================================== #
#  Shared test data
# =========================================================================== #

def make_event(**overrides) -> EventData:
    defaults = dict(
        title="Modern Calligraphy Basics",
        description="Learn the fundamentals of modern calligraphy!",
        start_date="04/15/2026", start_time="18:30:00",
        end_date="04/15/2026", end_time="20:30:00",
        timezone="America/New_York", all_day=False,
        event_url="https://example.com/event",
        ticket_max_capacity="30", custom_state="Massachusetts", custom_city="Boston",
        ticket_price="45.00",
        venue=Venue(venue_id=518716),
        organizer=Organizer(organizer_id=12345),
    )
    defaults.update(overrides)
    return EventData(**defaults)


def make_nonces(**overrides) -> FormNonces:
    defaults = dict(
        post_id="524553", wpnonce="d0a24d3d3c",
        virtual_nonce="79362addae", status_nonce="a06c4bb579", tickets_nonce="56436247f1",
    )
    defaults.update(overrides)
    return FormNonces(**defaults)


FAKE_FORM_HTML = textwrap.dedent("""\
    <html><body>
    <form method="post" enctype="multipart/form-data">
        <input type="hidden" name="post_ID" id="post_ID" value="524553"/>
        <input type="hidden" id="_wpnonce" name="_wpnonce" value="d0a24d3d3c" />
        <input type="hidden" name="_wp_http_referer" value="/allevents/squad/add" />
        <input type="hidden" id="tribe-events-virtual[virtual-nonce]"
               name="tribe-events-virtual[virtual-nonce]" value="79362addae" />
        <input type="hidden" id="tribe-events-status[nonce]"
               name="tribe-events-status[nonce]" value="a06c4bb579" />
        <input type="hidden" id="tribe-tickets-post-settings"
               name="tribe-tickets-post-settings" value="56436247f1" />
        <input type="text" name="post_title" value="" />
        <input type="submit" name="community-event" value="Submit Event"/>
    </form>
    </body></html>
""")

FAKE_ERROR_HTML = '<div class="tribe-community-notice"><p>Event Title is required</p></div>'


# =========================================================================== #
#  UNIT TESTS — Models
# =========================================================================== #

class TestEventDataValidation(unittest.TestCase):

    def test_valid_event_no_errors(self):
        self.assertEqual(make_event().validate(), [])

    def test_missing_title(self):
        errors = make_event(title="").validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("title", errors[0].lower())

    def test_missing_description(self):
        errors = make_event(description="").validate()
        self.assertIn("description", errors[0].lower())

    def test_missing_all_required_fields(self):
        errors = EventData().validate()
        self.assertEqual(len(errors), 6)

    def test_optional_fields_dont_cause_errors(self):
        event = make_event(event_url="", ticket_max_capacity="", custom_state="")
        self.assertEqual(event.validate(), [])

    def test_default_timezone(self):
        self.assertEqual(EventData().timezone, "America/New_York")

    def test_default_all_day_false(self):
        self.assertFalse(EventData().all_day)


class TestVenue(unittest.TestCase):

    def test_venue_with_id(self):
        v = Venue(venue_id=518716)
        self.assertEqual(v.venue_id, 518716)
        self.assertEqual(v.name, "")

    def test_venue_default_country(self):
        self.assertEqual(Venue().country, "United States")

    def test_venue_full_details(self):
        v = Venue(name="Test Place", city="Boston", state="MA")
        self.assertIsNone(v.venue_id)
        self.assertEqual(v.city, "Boston")


class TestOrganizer(unittest.TestCase):

    def test_organizer_with_id(self):
        o = Organizer(organizer_id=42)
        self.assertEqual(o.organizer_id, 42)

    def test_organizer_with_details(self):
        o = Organizer(name="Jane", email="j@test.com")
        self.assertEqual(o.email, "j@test.com")


class TestAuthResult(unittest.TestCase):

    def test_success(self):
        r = AuthResult(status=AuthStatus.SUCCESS, message="ok")
        self.assertTrue(r.is_success)
        self.assertFalse(r.needs_manual_intervention)

    def test_failure(self):
        r = AuthResult(status=AuthStatus.FAILED_CREDENTIALS, message="bad")
        self.assertFalse(r.is_success)

    def test_captcha_needs_manual(self):
        r = AuthResult(status=AuthStatus.FAILED_CAPTCHA, message="captcha")
        self.assertTrue(r.needs_manual_intervention)

    def test_2fa_needs_manual(self):
        r = AuthResult(status=AuthStatus.FAILED_2FA, message="2fa")
        self.assertTrue(r.needs_manual_intervention)

    def test_network_does_not_need_manual(self):
        r = AuthResult(status=AuthStatus.FAILED_NETWORK, message="network")
        self.assertFalse(r.needs_manual_intervention)


# =========================================================================== #
#  UNIT TESTS — NonceExtractor
# =========================================================================== #

class TestNonceExtractor(unittest.TestCase):

    def test_extracts_all_nonces(self):
        p = NonceExtractor()
        p.feed(FAKE_FORM_HTML)
        self.assertEqual(p.values["post_ID"], "524553")
        self.assertEqual(p.values["_wpnonce"], "d0a24d3d3c")
        self.assertEqual(p.values["tribe-events-virtual[virtual-nonce]"], "79362addae")
        self.assertEqual(p.values["tribe-events-status[nonce]"], "a06c4bb579")
        self.assertEqual(p.values["tribe-tickets-post-settings"], "56436247f1")

    def test_ignores_non_hidden_inputs(self):
        p = NonceExtractor()
        p.feed('<input type="text" name="title" value="Hello" />')
        self.assertNotIn("title", p.values)

    def test_empty_html(self):
        p = NonceExtractor()
        p.feed("")
        self.assertEqual(p.values, {})


# =========================================================================== #
#  UNIT TESTS — Form data builder
# =========================================================================== #

class TestBuildFormData(unittest.TestCase):

    def setUp(self):
        self.submitter = EventSubmitter(cookies={"fake": "c"}, delay_seconds=0)

    def test_nonces_included(self):
        data = self.submitter._build_form_data(make_event(), make_nonces())
        self.assertEqual(data["_wpnonce"], "d0a24d3d3c")
        self.assertEqual(data["post_ID"], "524553")

    def test_core_fields_included(self):
        data = self.submitter._build_form_data(make_event(), make_nonces())
        self.assertEqual(data["post_title"], "Modern Calligraphy Basics")
        self.assertEqual(data["EventStartDate"], "04/15/2026")
        self.assertEqual(data["EventStartTime"], "18:30:00")

    def test_custom_fields_included(self):
        data = self.submitter._build_form_data(make_event(), make_nonces())
        self.assertEqual(data["_ecp_custom_3"], "30")
        self.assertEqual(data["_ecp_custom_5"], "Massachusetts")
        self.assertEqual(data["_ecp_custom_10"], "Boston")

    def test_submit_button(self):
        data = self.submitter._build_form_data(make_event(), make_nonces())
        self.assertEqual(data["community-event"], "Submit Event")

    def test_existing_venue_id(self):
        event = make_event(venue=Venue(venue_id=518716))
        data = self.submitter._build_form_data(event, make_nonces())
        self.assertEqual(data["venue[VenueID][]"], "518716")
        self.assertNotIn("venue[Venue][]", data)

    def test_new_venue_details(self):
        event = make_event(venue=Venue(name="New Place", city="Cambridge"))
        data = self.submitter._build_form_data(event, make_nonces())
        self.assertEqual(data["venue[VenueID][]"], "-1")
        self.assertEqual(data["venue[Venue][]"], "New Place")

    def test_existing_organizer_id(self):
        event = make_event(organizer=Organizer(organizer_id=99))
        data = self.submitter._build_form_data(event, make_nonces())
        self.assertEqual(data["organizer[OrganizerID][]"], "99")

    def test_new_organizer_details(self):
        event = make_event(organizer=Organizer(name="Jane", email="j@x.com"))
        data = self.submitter._build_form_data(event, make_nonces())
        self.assertEqual(data["organizer[OrganizerID][]"], "-1")
        self.assertEqual(data["organizer[Organizer][]"], "Jane")

    def test_all_day_flag(self):
        data = self.submitter._build_form_data(make_event(all_day=True), make_nonces())
        self.assertEqual(data["EventAllDay"], "yes")

    def test_no_all_day_flag(self):
        data = self.submitter._build_form_data(make_event(all_day=False), make_nonces())
        self.assertNotIn("EventAllDay", data)


# =========================================================================== #
#  UNIT TESTS — Error extraction
# =========================================================================== #

class TestExtractFormErrors(unittest.TestCase):

    def test_extracts_error_text(self):
        err = EventSubmitter._extract_form_errors(FAKE_ERROR_HTML)
        self.assertIn("Title", err)

    def test_no_errors_returns_empty(self):
        err = EventSubmitter._extract_form_errors("<html><body>ok</body></html>")
        self.assertEqual(err, "")

    def test_strips_html_tags(self):
        html = '<div class="tribe-community-notice"><p><b>Error:</b> Bad</p></div>'
        err = EventSubmitter._extract_form_errors(html)
        self.assertNotIn("<", err)


# =========================================================================== #
#  UNIT TESTS — CSV parser
# =========================================================================== #

class TestCsvParser(unittest.TestCase):

    def _write_csv(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        f.write(content)
        f.close()
        return Path(f.name)

    def test_parses_two_events(self):
        from core.csv_parser import parse_csv
        csv = self._write_csv(
            'title,description,start_date,start_time,end_date,end_time\n'
            '"A","Desc A","04/01/2026","10:00:00","04/01/2026","12:00:00"\n'
            '"B","Desc B","04/02/2026","11:00:00","04/02/2026","13:00:00"\n'
        )
        events = parse_csv(csv)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].title, "A")
        self.assertEqual(events[1].title, "B")

    def test_missing_file_raises(self):
        from core.csv_parser import parse_csv
        with self.assertRaises(FileNotFoundError):
            parse_csv("/no/such/file.csv")

    def test_venue_id_parsed(self):
        from core.csv_parser import parse_csv
        csv = self._write_csv(
            'title,description,start_date,start_time,end_date,end_time,venue_id\n'
            '"T","D","01/01/2026","09:00:00","01/01/2026","11:00:00","518716"\n'
        )
        events = parse_csv(csv)
        self.assertEqual(events[0].venue.venue_id, 518716)

    def test_empty_venue_id_is_none(self):
        from core.csv_parser import parse_csv
        csv = self._write_csv(
            'title,description,start_date,start_time,end_date,end_time,venue_id\n'
            '"T","D","01/01/2026","09:00:00","01/01/2026","11:00:00",""\n'
        )
        events = parse_csv(csv)
        self.assertIsNone(events[0].venue.venue_id)

    def test_whitespace_stripped(self):
        from core.csv_parser import parse_csv
        csv = self._write_csv(
            'title,description,start_date,start_time,end_date,end_time\n'
            '"  Spaced  ","  desc  ","04/15/2026","18:00:00","04/15/2026","20:00:00"\n'
        )
        events = parse_csv(csv)
        self.assertEqual(events[0].title, "Spaced")

    def test_missing_required_fields_still_returned(self):
        from core.csv_parser import parse_csv
        csv = self._write_csv(
            'title,description,start_date,start_time,end_date,end_time\n'
            '"","","","","",""\n'
        )
        events = parse_csv(csv)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].validate()), 6)


# =========================================================================== #
#  UNIT TESTS — Authenticator
# =========================================================================== #

class TestAuthenticator(unittest.TestCase):

    def test_login_success(self):
        from core.authenticator import Authenticator
        from auth.base import AuthStrategy

        class FakeStrategy(AuthStrategy):
            def authenticate(self):
                return AuthResult(status=AuthStatus.SUCCESS, message="ok",
                                  cookies={"wp": "cookie"})
            def is_authenticated(self): return True
            def close(self): pass

        auth = Authenticator(FakeStrategy())
        result = auth.login()
        self.assertTrue(result.is_success)

    def test_login_failure(self):
        from core.authenticator import Authenticator
        from auth.base import AuthStrategy

        class FakeStrategy(AuthStrategy):
            def authenticate(self):
                return AuthResult(status=AuthStatus.FAILED_CREDENTIALS, message="bad")
            def is_authenticated(self): return False
            def close(self): pass

        auth = Authenticator(FakeStrategy())
        result = auth.login()
        self.assertFalse(result.is_success)

    def test_strategy_swap(self):
        from core.authenticator import Authenticator
        from auth.base import AuthStrategy

        class Fail(AuthStrategy):
            closed = False
            def authenticate(self):
                return AuthResult(status=AuthStatus.FAILED_CREDENTIALS, message="fail")
            def is_authenticated(self): return False
            def close(self): self.closed = True

        class Pass(AuthStrategy):
            def authenticate(self):
                return AuthResult(status=AuthStatus.SUCCESS, message="pass")
            def is_authenticated(self): return True
            def close(self): pass

        fail_strat = Fail()
        auth = Authenticator(fail_strat)
        self.assertFalse(auth.login().is_success)

        auth.strategy = Pass()
        self.assertTrue(fail_strat.closed)
        self.assertTrue(auth.login().is_success)


# =========================================================================== #
#  INTEGRATION TESTS — Mock WordPress Server
# =========================================================================== #

class MockWPHandler(BaseHTTPRequestHandler):
    valid_cookie = "test_session"

    def do_GET(self):
        if not self._authed():
            self.send_response(302)
            self.send_header("Location", "/wp-login.php")
            self.end_headers()
            return

        if "/allevents/squad/add" in self.path:
            self._respond(200, FAKE_FORM_HTML)
        elif "/allevents/squad/list" in self.path:
            self._respond(200, "<html>Event list</html>")
        else:
            self._respond(404, "Not found")

    def do_POST(self):
        if not self._authed():
            self.send_response(302)
            self.send_header("Location", "/wp-login.php")
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        params = parse_qs(body)

        title = params.get("post_title", [""])[0]
        nonce = params.get("_wpnonce", [""])[0]

        if not title or not nonce:
            self._respond(200, FAKE_ERROR_HTML)
        else:
            self.send_response(302)
            self.send_header("Location", "/allevents/squad/list/")
            self.end_headers()

    def _authed(self):
        return self.valid_cookie in self.headers.get("Cookie", "")

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a):
        pass


class TestIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockWPHandler)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

        # Patch the form URL
        import core.submitter as mod
        cls._original_url = mod.FORM_URL
        mod.FORM_URL = f"{cls.base_url}/allevents/squad/add"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        import core.submitter as mod
        mod.FORM_URL = cls._original_url

    def _make_submitter(self, cookie="test_session"):
        s = EventSubmitter(cookies={}, delay_seconds=0)
        s._session.cookies.clear()
        s._session.cookies.set("session", cookie)
        return s

    def test_fetch_nonces_from_mock(self):
        s = self._make_submitter()
        nonces = s._fetch_nonces()
        self.assertEqual(nonces.wpnonce, "d0a24d3d3c")
        self.assertEqual(nonces.post_id, "524553")

    def test_successful_submit(self):
        s = self._make_submitter()
        result = s.submit(make_event())
        self.assertTrue(result.success, f"Expected success but got: {result.message}")

    def test_submit_without_auth_fails(self):
        s = self._make_submitter(cookie="bad_cookie")
        result = s.submit(make_event())
        self.assertFalse(result.success)

    def test_submit_empty_title_fails(self):
        s = self._make_submitter()
        result = s.submit(make_event(title=""))
        self.assertFalse(result.success)

    def test_batch_submit_three_events(self):
        s = self._make_submitter()
        events = [make_event(title=f"Event {i}") for i in range(3)]
        results = s.submit_batch(events)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.success for r in results))

    def test_csv_to_submit_end_to_end(self):
        from core.csv_parser import parse_csv
        csv_content = (
            'title,description,start_date,start_time,end_date,end_time\n'
            '"Test A","Desc","04/15/2026","18:00:00","04/15/2026","20:00:00"\n'
            '"Test B","Desc","04/16/2026","18:00:00","04/16/2026","20:00:00"\n'
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        events = parse_csv(csv_path)
        s = self._make_submitter()
        results = s.submit_batch(events)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.success for r in results))


# =========================================================================== #
#  Runner
# =========================================================================== #

def main():
    parser = argparse.ArgumentParser(description="Run autoposter tests")
    parser.add_argument("--unit", action="store_true", help="Unit tests only")
    parser.add_argument("--integ", action="store_true", help="Integration tests only")
    args = parser.parse_args()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    unit_classes = [
        TestEventDataValidation, TestVenue, TestOrganizer, TestAuthResult,
        TestNonceExtractor, TestBuildFormData, TestExtractFormErrors,
        TestCsvParser, TestAuthenticator,
    ]
    integ_classes = [TestIntegration]

    if args.unit:
        for cls in unit_classes:
            suite.addTests(loader.loadTestsFromTestCase(cls))
    elif args.integ:
        for cls in integ_classes:
            suite.addTests(loader.loadTestsFromTestCase(cls))
    else:
        for cls in unit_classes + integ_classes:
            suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
