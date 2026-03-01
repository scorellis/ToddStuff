"""
Data models for Sip & Script events — mapped from the actual form fields.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Venue:
    """Venue for an event. Use venue_id for existing venues, or fill in details for new."""
    venue_id: Optional[int] = None       # Use existing venue ID from dropdown
    name: str = ""                        # venue[Venue][]
    address: str = ""                     # venue[Address][]
    city: str = ""                        # venue[City][]
    state: str = ""                       # venue[State][]
    zip_code: str = ""                    # venue[Zip][]
    country: str = "United States"        # venue[Country][]
    phone: str = ""                       # venue[Phone][]
    url: str = ""                         # venue[URL][]


@dataclass
class Organizer:
    """Event organizer. Use organizer_id for existing, or fill in details for new."""
    organizer_id: Optional[int] = None    # Use existing organizer ID
    name: str = ""                        # organizer[Organizer][]
    phone: str = ""                       # organizer[Phone][]
    website: str = ""                     # organizer[Website][]
    email: str = ""                       # organizer[Email][]


@dataclass
class EventData:
    """
    Represents a single class/event to post to Sip & Script.
    Maps directly to the Community Events form fields.
    """
    # Required
    title: str = ""                       # post_title
    description: str = ""                 # tcepostcontent
    start_date: str = ""                  # EventStartDate — MM/DD/YYYY
    start_time: str = ""                  # EventStartTime — HH:MM:SS
    end_date: str = ""                    # EventEndDate — MM/DD/YYYY
    end_time: str = ""                    # EventEndTime — HH:MM:SS

    # Optional
    timezone: str = "America/New_York"    # EventTimezone
    all_day: bool = False                 # EventAllDay
    event_url: str = ""                   # EventURL (external link)

    # Custom fields
    ticket_max_capacity: str = ""         # _ecp_custom_3
    custom_state: str = ""               # _ecp_custom_5
    custom_city: str = ""                # _ecp_custom_10

    # Related objects
    venue: Venue = field(default_factory=Venue)
    organizer: Organizer = field(default_factory=Organizer)

    # Ticket info (optional)
    ticket_price: str = ""
    ticket_description: str = ""

    def validate(self) -> list[str]:
        """Return list of validation errors."""
        errors = []
        if not self.title:
            errors.append("Event title is required")
        if not self.description:
            errors.append("Event description is required")
        if not self.start_date:
            errors.append("Start date is required (MM/DD/YYYY)")
        if not self.start_time:
            errors.append("Start time is required (HH:MM:SS)")
        if not self.end_date:
            errors.append("End date is required (MM/DD/YYYY)")
        if not self.end_time:
            errors.append("End time is required (HH:MM:SS)")
        return errors
