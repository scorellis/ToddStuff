"""
CSV parser for reading class schedules into EventData objects.
Single Responsibility: only handles CSV → EventData conversion.
"""

import csv
from pathlib import Path

from models.event import EventData, Venue, Organizer
from utils.logger import get_logger

logger = get_logger(__name__)

# Map CSV column headers to EventData fields.
# Adjust the left side (CSV headers) to match YOUR actual CSV columns.
DEFAULT_COLUMN_MAP = {
    "title": "title",
    "event_title": "title",
    "name": "title",
    "description": "description",
    "event_description": "description",
    "start_date": "start_date",
    "start date": "start_date",
    "start_time": "start_time",
    "start time": "start_time",
    "end_date": "end_date",
    "end date": "end_date",
    "end_time": "end_time",
    "end time": "end_time",
    "timezone": "timezone",
    "event_url": "event_url",
    "url": "event_url",
    "link": "event_url",
    "capacity": "ticket_max_capacity",
    "max_capacity": "ticket_max_capacity",
    "ticket_max_capacity": "ticket_max_capacity",
    "state": "custom_state",
    "city": "custom_city",
    "venue_name": "venue_name",
    "venue": "venue_name",
    "venue_id": "venue_id",
    "venue_address": "venue_address",
    "address": "venue_address",
    "venue_city": "venue_city",
    "venue_state": "venue_state",
    "venue_zip": "venue_zip",
    "zip": "venue_zip",
    "venue_phone": "venue_phone",
    "organizer_name": "organizer_name",
    "organizer": "organizer_name",
    "organizer_id": "organizer_id",
    "organizer_email": "organizer_email",
    "organizer_phone": "organizer_phone",
    "organizer_website": "organizer_website",
    "ticket_price": "ticket_price",
    "price": "ticket_price",
}


def parse_csv(
    filepath,
    column_map=None,
) -> list:
    """
    Parse a CSV file into a list of EventData objects.

    Args:
        filepath: Path to the CSV file.
        column_map: Optional custom mapping of CSV headers → EventData fields.
                    Falls back to DEFAULT_COLUMN_MAP.

    Returns:
        List of validated EventData objects.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"CSV not found: {filepath}")

    cmap = column_map or DEFAULT_COLUMN_MAP
    events = []

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError("CSV file has no headers")

        # Log which columns we found
        mapped = []
        unmapped = []
        for col in reader.fieldnames:
            normalized = col.strip().lower()
            if normalized in cmap:
                mapped.append(f"  '{col}' → {cmap[normalized]}")
            else:
                unmapped.append(col)

        logger.info(f"CSV columns mapped:\n" + "\n".join(mapped))
        if unmapped:
            logger.warning(f"CSV columns not mapped (will be ignored): {unmapped}")

        for row_num, row in enumerate(reader, start=2):  # row 1 = headers
            try:
                event = _row_to_event(row, cmap)
                errors = event.validate()
                if errors:
                    logger.warning(f"Row {row_num}: validation errors: {errors}")
                events.append(event)
            except Exception as e:
                logger.error(f"Row {row_num}: failed to parse — {e}")

    logger.info(f"Parsed {len(events)} events from {filepath.name}")
    return events


def _row_to_event(row: dict[str, str], cmap: dict[str, str]) -> EventData:
    """Convert a single CSV row dict into an EventData object."""
    # Collect mapped values
    values: dict[str, str] = {}
    for csv_col, csv_val in row.items():
        normalized = csv_col.strip().lower()
        if normalized in cmap:
            field_name = cmap[normalized]
            values[field_name] = csv_val.strip() if csv_val else ""

    # Build venue
    venue = Venue(
        venue_id=int(values["venue_id"]) if values.get("venue_id") else None,
        name=values.get("venue_name", ""),
        address=values.get("venue_address", ""),
        city=values.get("venue_city", ""),
        state=values.get("venue_state", ""),
        zip_code=values.get("venue_zip", ""),
        phone=values.get("venue_phone", ""),
    )

    # Build organizer
    organizer = Organizer(
        organizer_id=int(values["organizer_id"]) if values.get("organizer_id") else None,
        name=values.get("organizer_name", ""),
        phone=values.get("organizer_phone", ""),
        website=values.get("organizer_website", ""),
        email=values.get("organizer_email", ""),
    )

    return EventData(
        title=values.get("title", ""),
        description=values.get("description", ""),
        start_date=values.get("start_date", ""),
        start_time=values.get("start_time", ""),
        end_date=values.get("end_date", ""),
        end_time=values.get("end_time", ""),
        timezone=values.get("timezone", "America/New_York"),
        event_url=values.get("event_url", ""),
        ticket_max_capacity=values.get("ticket_max_capacity", ""),
        custom_state=values.get("custom_state", ""),
        custom_city=values.get("custom_city", ""),
        ticket_price=values.get("ticket_price", ""),
        venue=venue,
        organizer=organizer,
    )
