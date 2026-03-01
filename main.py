#!/usr/bin/env python3
"""
Sip & Script Autoposter

Usage:
    python main.py --login                  # Step 1: Log in and save cookies
    python main.py --login --manual         # Step 1 (manual): You complete Google login
    python main.py --submit events.csv      # Step 2: Submit events from CSV
    python main.py --dry-run events.csv     # Preview what would be submitted
    python main.py --test-session           # Check if saved cookies still work

Workflow:
    1. Run --login (or --login --manual) once to authenticate and save cookies
    2. Run --submit <csv_file> to post all events from the CSV
    3. Cookies persist in session_cookies.json — reuse until they expire
"""

import argparse
import json
import sys
from pathlib import Path

from config import AppConfig
from auth import SeleniumAuthStrategy
from core.authenticator import Authenticator
from core.csv_parser import parse_csv
from core.submitter import EventSubmitter
from utils.logger import get_logger

logger = get_logger("main")
COOKIE_FILE = Path("session_cookies.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sip & Script Autoposter — Submit events from CSV"
    )
    parser.add_argument(
        "--login", action="store_true",
        help="Log in via browser and save session cookies",
    )
    parser.add_argument(
        "--manual", action="store_true",
        help="Manual login mode: you complete Google sign-in in the browser",
    )
    parser.add_argument(
        "--submit", metavar="CSV_FILE",
        help="Submit events from a CSV file using saved cookies",
    )
    parser.add_argument(
        "--dry-run", metavar="CSV_FILE",
        help="Parse CSV and show what would be submitted (no actual POST)",
    )
    parser.add_argument(
        "--test-session", action="store_true",
        help="Test if saved session cookies are still valid",
    )
    parser.add_argument(
        "--delay", type=float, default=3.0,
        help="Seconds to wait between submissions (default: 3)",
    )
    return parser.parse_args()


def cmd_login(manual: bool) -> int:
    """Handle --login: authenticate and save cookies."""
    config = AppConfig()
    if manual:
        config = AppConfig(
            auth=config.auth.__class__(
                google_email="",
                google_password="",
                login_timeout=config.auth.login_timeout,
                manual_mode=True,
            ),
            site=config.site,
            browser=config.browser,
        )

    strategy = SeleniumAuthStrategy(config)
    authenticator = Authenticator(strategy)

    try:
        result = authenticator.login()
        if result.is_success:
            print(f"\n✅ Login successful! Cookies saved to {COOKIE_FILE}")
            print("   You can now run: python main.py --submit your_events.csv")
            return 0
        else:
            print(f"\n❌ Login failed: {result.message}")
            return 1
    finally:
        authenticator.cleanup()


def cmd_test_session() -> int:
    """Handle --test-session: check if cookies are valid."""
    if not COOKIE_FILE.exists():
        print(f"❌ No cookie file found at {COOKIE_FILE}")
        print("   Run: python main.py --login")
        return 1

    with open(COOKIE_FILE) as f:
        cookies = json.load(f)

    print(f"Found {len(cookies)} cookies. Testing session...")
    submitter = EventSubmitter(cookies)
    nonces = submitter._fetch_nonces()

    if nonces.wpnonce:
        print(f"✅ Session is valid! Got nonce: {nonces.wpnonce[:6]}...")
        print("   You can submit events.")
        return 0
    else:
        print("❌ Session expired. Please re-login:")
        print("   python main.py --login --manual")
        return 1


def cmd_dry_run(csv_file: str) -> int:
    """Handle --dry-run: parse and display events without submitting."""
    events = parse_csv(csv_file)

    if not events:
        print("❌ No events found in CSV.")
        return 1

    print(f"\n📋 Found {len(events)} events:\n")
    for i, e in enumerate(events, 1):
        errors = e.validate()
        status = "✅" if not errors else f"⚠️  ({', '.join(errors)})"

        print(f"  {i}. {e.title or '(no title)'}")
        print(f"     Date: {e.start_date} {e.start_time} → {e.end_date} {e.end_time}")
        print(f"     Venue: {e.venue.name or f'ID #{e.venue.venue_id}' or '(none)'}")
        print(f"     State: {e.custom_state}  City: {e.custom_city}")
        print(f"     Status: {status}")
        print()

    valid = sum(1 for e in events if not e.validate())
    print(f"📊 {valid}/{len(events)} events are valid and ready to submit.")
    return 0


def cmd_submit(csv_file: str, delay: float) -> int:
    """Handle --submit: parse CSV and submit all events."""
    # Check cookies
    if not COOKIE_FILE.exists():
        print(f"❌ No cookie file found. Please login first:")
        print("   python main.py --login --manual")
        return 1

    with open(COOKIE_FILE) as f:
        cookies = json.load(f)

    # Parse CSV
    events = parse_csv(csv_file)
    if not events:
        print("❌ No events found in CSV.")
        return 1

    # Validate
    invalid = [(i, e) for i, e in enumerate(events, 1) if e.validate()]
    if invalid:
        print(f"⚠️  {len(invalid)} events have validation issues:")
        for row_num, e in invalid:
            print(f"   Row {row_num} '{e.title}': {e.validate()}")
        print()

        response = input("Continue with valid events only? [y/N] ").strip().lower()
        if response != "y":
            return 1

    valid_events = [e for e in events if not e.validate()]
    print(f"\n🚀 Submitting {len(valid_events)} events (delay: {delay}s between each)...\n")

    # Submit
    submitter = EventSubmitter(cookies, delay_seconds=delay)
    results = submitter.submit_batch(valid_events)

    # Report
    print("\n" + "=" * 60)
    print("  SUBMISSION REPORT")
    print("=" * 60)
    for r in results:
        icon = "✅" if r.success else "❌"
        print(f"  {icon} {r.event_title}: {r.message}")

    successes = sum(1 for r in results if r.success)
    print(f"\n  Total: {successes}/{len(results)} succeeded")
    print("=" * 60)

    return 0 if successes == len(results) else 1


def main() -> int:
    args = parse_args()

    if args.login:
        return cmd_login(manual=args.manual)
    elif args.test_session:
        return cmd_test_session()
    elif args.dry_run:
        return cmd_dry_run(args.dry_run)
    elif args.submit:
        return cmd_submit(args.submit, delay=args.delay)
    else:
        print("No action specified. Use --help for usage info.")
        print("\nQuick start:")
        print("  1. python main.py --login --manual")
        print("  2. python main.py --dry-run events.csv")
        print("  3. python main.py --submit events.csv")
        return 0


if __name__ == "__main__":
    sys.exit(main())
