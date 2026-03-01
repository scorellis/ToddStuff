"""
Form submitter for The Events Calendar Community Events.

Two-step process per submission:
1. GET the form page → extract fresh nonces and post_ID
2. POST the form data with all required fields

Depends on having valid WordPress session cookies (from SeleniumAuthStrategy).
"""

import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser

import requests

from models.event import EventData
from utils.logger import get_logger

logger = get_logger(__name__)

FORM_URL = "https://sipandscript.com/allevents/squad/add"


@dataclass
class FormNonces:
    """Security tokens extracted from the form page. All are required for POST."""
    post_id: str = ""
    wpnonce: str = ""
    virtual_nonce: str = ""
    status_nonce: str = ""
    tickets_nonce: str = ""


@dataclass
class SubmitResult:
    """Outcome of a single event submission."""
    success: bool
    event_title: str
    message: str
    http_status: int = 0


class NonceExtractor(HTMLParser):
    """Simple HTML parser to extract hidden input values by name."""

    def __init__(self):
        super().__init__()
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list):
        if tag != "input":
            return
        attr_dict = dict(attrs)
        if attr_dict.get("type") == "hidden" and "name" in attr_dict and "value" in attr_dict:
            self.values[attr_dict["name"]] = attr_dict.get("value", "")


class EventSubmitter:
    """
    Submits events to Sip & Script's Community Events form.

    Usage:
        submitter = EventSubmitter(cookies={"wordpress_logged_in_xxx": "..."})
        result = submitter.submit(event_data)
    """

    def __init__(self, cookies: dict[str, str], delay_seconds: float = 3.0):
        self._session = requests.Session()
        for name, value in cookies.items():
            self._session.cookies.set(name, value, domain="sipandscript.com")
        self._delay = delay_seconds

        # Set realistic headers
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": FORM_URL,
        })

    def submit(self, event: EventData) -> SubmitResult:
        """Submit a single event. Fetches fresh nonces first."""
        logger.info(f"Submitting: {event.title}")

        # Step 1: GET the form page for fresh nonces
        nonces = self._fetch_nonces()
        if not nonces.wpnonce:
            return SubmitResult(
                success=False,
                event_title=event.title,
                message="Failed to fetch form page or extract nonces. Session may have expired.",
            )

        # Step 2: Build and POST the form data
        form_data = self._build_form_data(event, nonces)
        try:
            resp = self._session.post(
                FORM_URL,
                data=form_data,
                timeout=30,
                allow_redirects=True,
            )

            # Check for success — the plugin typically redirects to the event
            # list or the edit page on success
            if resp.status_code == 200 and "allevents/squad/list" in resp.url:
                logger.info(f"✅ Submitted successfully: {event.title}")
                return SubmitResult(
                    success=True,
                    event_title=event.title,
                    message=f"Event submitted. Redirected to: {resp.url}",
                    http_status=resp.status_code,
                )

            # Check if we got redirected back to the form (validation error)
            if "squad/add" in resp.url or "squad/edit" in resp.url:
                # Try to extract error messages
                errors = self._extract_form_errors(resp.text)
                msg = f"Form validation error: {errors}" if errors else "Unknown form error"
                logger.warning(f"⚠️  {event.title}: {msg}")
                return SubmitResult(
                    success=False,
                    event_title=event.title,
                    message=msg,
                    http_status=resp.status_code,
                )

            # Other outcomes
            return SubmitResult(
                success=False,
                event_title=event.title,
                message=f"Unexpected response. Status: {resp.status_code}, URL: {resp.url}",
                http_status=resp.status_code,
            )

        except requests.RequestException as e:
            return SubmitResult(
                success=False,
                event_title=event.title,
                message=f"HTTP error: {str(e)[:200]}",
            )
        finally:
            # Rate-limit between submissions
            time.sleep(self._delay)

    def submit_batch(self, events: list[EventData]) -> list[SubmitResult]:
        """Submit multiple events, collecting results."""
        results = []
        for i, event in enumerate(events, 1):
            logger.info(f"--- Event {i}/{len(events)} ---")
            result = self.submit(event)
            results.append(result)

            if not result.success and "expired" in result.message.lower():
                logger.error("Session appears expired. Stopping batch.")
                break

        # Summary
        successes = sum(1 for r in results if r.success)
        failures = len(results) - successes
        logger.info(f"\n📊 Batch complete: {successes} succeeded, {failures} failed")

        return results

    def _fetch_nonces(self) -> FormNonces:
        """GET the form page and extract all required nonces."""
        try:
            resp = self._session.get(FORM_URL, timeout=15)

            if resp.status_code != 200:
                logger.error(f"Form page returned HTTP {resp.status_code}")
                return FormNonces()

            if "wp-login" in resp.url:
                logger.error("Redirected to login page — session cookies are invalid/expired.")
                return FormNonces()

            # Parse hidden inputs
            parser = NonceExtractor()
            parser.feed(resp.text)
            hidden = parser.values

            nonces = FormNonces(
                post_id=hidden.get("post_ID", ""),
                wpnonce=hidden.get("_wpnonce", ""),
                virtual_nonce=hidden.get("tribe-events-virtual[virtual-nonce]", ""),
                status_nonce=hidden.get("tribe-events-status[nonce]", ""),
                tickets_nonce=hidden.get("tribe-tickets-post-settings", ""),
            )

            logger.info(
                f"Nonces fetched — post_ID={nonces.post_id}, "
                f"wpnonce={nonces.wpnonce[:6]}..."
            )
            return nonces

        except requests.RequestException as e:
            logger.error(f"Failed to fetch form page: {e}")
            return FormNonces()

    def _build_form_data(self, event: EventData, nonces: FormNonces) -> dict:
        """Build the complete form payload."""
        data = {
            # Hidden fields / nonces
            "post_ID": nonces.post_id,
            "_wpnonce": nonces.wpnonce,
            "_wp_http_referer": "/allevents/squad/add",
            "tribe-events-virtual[virtual-nonce]": nonces.virtual_nonce,
            "tribe-events-status[nonce]": nonces.status_nonce,
            "tribe-tickets-post-settings": nonces.tickets_nonce,

            # Core event fields
            "post_title": event.title,
            "tcepostcontent": event.description,
            "EventStartDate": event.start_date,
            "EventStartTime": event.start_time,
            "EventEndDate": event.end_date,
            "EventEndTime": event.end_time,
            "EventTimezone": event.timezone,

            # External link
            "EventURL": event.event_url,

            # Custom fields
            "_ecp_custom_3": event.ticket_max_capacity,
            "_ecp_custom_5": event.custom_state,
            "_ecp_custom_10": event.custom_city,

            # Submit button
            "community-event": "Submit Event",
        }

        # All-day event
        if event.all_day:
            data["EventAllDay"] = "yes"

        # Venue — use existing ID or create new
        v = event.venue
        if v.venue_id:
            data["venue[VenueID][]"] = str(v.venue_id)
        else:
            data["venue[VenueID][]"] = "-1"
            data["venue[Venue][]"] = v.name
            data["venue[Address][]"] = v.address
            data["venue[City][]"] = v.city
            data["venue[State][]"] = v.state
            data["venue[Zip][]"] = v.zip_code
            data["venue[Country][]"] = v.country
            data["venue[Phone][]"] = v.phone
            data["venue[URL][]"] = v.url

        # Organizer — use existing ID or create new
        o = event.organizer
        if o.organizer_id:
            data["organizer[OrganizerID][]"] = str(o.organizer_id)
        else:
            data["organizer[OrganizerID][]"] = "-1"
            data["organizer[Organizer][]"] = o.name
            data["organizer[Phone][]"] = o.phone
            data["organizer[Website][]"] = o.website
            data["organizer[Email][]"] = o.email

        return data

    @staticmethod
    def _extract_form_errors(html: str) -> str:
        """Try to extract validation error messages from the response page."""
        # The plugin shows errors in .tribe-community-notice elements
        pattern = r'class="tribe-community-notice[^"]*"[^>]*>(.*?)</div>'
        matches = re.findall(pattern, html, re.DOTALL)
        if matches:
            # Strip HTML tags from error messages
            clean = re.sub(r"<[^>]+>", "", " ".join(matches)).strip()
            return clean[:500]
        return ""
