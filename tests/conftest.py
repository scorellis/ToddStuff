"""
Shared pytest fixtures for autoposter tests.
"""

import pytest
import textwrap
from pathlib import Path

from models.event import EventData, Venue, Organizer
from models.auth_result import AuthResult, AuthStatus
from core.submitter import FormNonces


# --------------------------------------------------------------------------- #
#  Factory helpers — build valid objects, override only what you need
# --------------------------------------------------------------------------- #

def make_event(**overrides) -> EventData:
    """Create a valid EventData with sensible defaults. Override any field."""
    defaults = dict(
        title="Modern Calligraphy Basics",
        description="Learn the fundamentals of modern calligraphy!",
        start_date="04/15/2026",
        start_time="18:30:00",
        end_date="04/15/2026",
        end_time="20:30:00",
        timezone="America/New_York",
        all_day=False,
        event_url="https://example.com/event",
        ticket_max_capacity="30",
        custom_state="Massachusetts",
        custom_city="Boston",
        ticket_price="45.00",
        venue=Venue(venue_id=518716),
        organizer=Organizer(organizer_id=12345),
    )
    defaults.update(overrides)
    return EventData(**defaults)


def make_nonces(**overrides) -> FormNonces:
    """Create a valid FormNonces with sensible defaults."""
    defaults = dict(
        post_id="524553",
        wpnonce="d0a24d3d3c",
        virtual_nonce="79362addae",
        status_nonce="a06c4bb579",
        tickets_nonce="56436247f1",
    )
    defaults.update(overrides)
    return FormNonces(**defaults)


def make_auth_result(success: bool = True, **overrides) -> AuthResult:
    """Create an AuthResult."""
    if success:
        defaults = dict(
            status=AuthStatus.SUCCESS,
            message="Authenticated successfully.",
            cookies={"wordpress_logged_in_abc": "fakecookie123"},
        )
    else:
        defaults = dict(
            status=AuthStatus.FAILED_CREDENTIALS,
            message="Authentication failed.",
            cookies={},
        )
    defaults.update(overrides)
    return AuthResult(**defaults)


# --------------------------------------------------------------------------- #
#  Fake HTML page simulating the real form
# --------------------------------------------------------------------------- #

FAKE_FORM_HTML = textwrap.dedent("""\
    <html><body>
    <form method="post" enctype="multipart/form-data" data-datepicker_format="2">
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
        <textarea name="tcepostcontent"></textarea>
        <input type="submit" name="community-event" value="Submit Event"/>
    </form>
    </body></html>
""")

FAKE_SUCCESS_REDIRECT_URL = "https://sipandscript.com/allevents/squad/list/"
FAKE_FORM_URL = "https://sipandscript.com/allevents/squad/add"
FAKE_LOGIN_REDIRECT_URL = "https://sipandscript.com/wp-login.php?redirect_to=..."

FAKE_ERROR_HTML = textwrap.dedent("""\
    <html><body>
    <div class="tribe-community-notice tribe-community-notice--error">
        <p>Event Title is required</p>
    </div>
    </body></html>
""")


# --------------------------------------------------------------------------- #
#  CSV helpers
# --------------------------------------------------------------------------- #

SAMPLE_CSV_CONTENT = textwrap.dedent("""\
    title,description,start_date,start_time,end_date,end_time,state,city,venue_id,capacity,ticket_price
    "Modern Calligraphy","Learn calligraphy basics!","04/15/2026","18:30:00","04/15/2026","20:30:00","Massachusetts","Boston",518716,"30","45.00"
    "Brush Lettering","Explore brush pen techniques.","04/22/2026","19:00:00","04/22/2026","21:00:00","New York","Brooklyn",,"25","50.00"
""")

SAMPLE_CSV_MISSING_REQUIRED = textwrap.dedent("""\
    title,description,start_date,start_time,end_date,end_time
    "","","","","",""
""")

SAMPLE_CSV_ALTERNATE_HEADERS = textwrap.dedent("""\
    Event Title,Event Description,Start Date,Start Time,End Date,End Time,State,City
    "Workshop A","Description A","05/01/2026","10:00:00","05/01/2026","12:00:00","Texas","Austin"
""")


@pytest.fixture
def tmp_csv(tmp_path) -> Path:
    """Write the sample CSV to a temp file and return its path."""
    csv_file = tmp_path / "events.csv"
    csv_file.write_text(SAMPLE_CSV_CONTENT)
    return csv_file


@pytest.fixture
def tmp_csv_missing_fields(tmp_path) -> Path:
    csv_file = tmp_path / "bad_events.csv"
    csv_file.write_text(SAMPLE_CSV_MISSING_REQUIRED)
    return csv_file


@pytest.fixture
def tmp_csv_alt_headers(tmp_path) -> Path:
    csv_file = tmp_path / "alt_events.csv"
    csv_file.write_text(SAMPLE_CSV_ALTERNATE_HEADERS)
    return csv_file


@pytest.fixture
def valid_event() -> EventData:
    return make_event()


@pytest.fixture
def valid_nonces() -> FormNonces:
    return make_nonces()
