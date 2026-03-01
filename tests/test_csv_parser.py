"""
Unit tests for the CSV parser.
"""

import pytest
from pathlib import Path
from core.csv_parser import parse_csv, _row_to_event, DEFAULT_COLUMN_MAP


# =========================================================================== #
#  Happy path
# =========================================================================== #

class TestCsvParserHappyPath:

    def test_parses_correct_number_of_events(self, tmp_csv):
        events = parse_csv(tmp_csv)
        assert len(events) == 2

    def test_first_event_title(self, tmp_csv):
        events = parse_csv(tmp_csv)
        assert events[0].title == "Modern Calligraphy"

    def test_first_event_dates(self, tmp_csv):
        events = parse_csv(tmp_csv)
        assert events[0].start_date == "04/15/2026"
        assert events[0].start_time == "18:30:00"
        assert events[0].end_date == "04/15/2026"
        assert events[0].end_time == "20:30:00"

    def test_first_event_custom_fields(self, tmp_csv):
        events = parse_csv(tmp_csv)
        assert events[0].custom_state == "Massachusetts"
        assert events[0].custom_city == "Boston"
        assert events[0].ticket_max_capacity == "30"
        assert events[0].ticket_price == "45.00"

    def test_first_event_venue_id(self, tmp_csv):
        events = parse_csv(tmp_csv)
        assert events[0].venue.venue_id == 518716

    def test_second_event_no_venue_id(self, tmp_csv):
        """When venue_id is blank in CSV, it should be None."""
        events = parse_csv(tmp_csv)
        assert events[1].venue.venue_id is None

    def test_default_timezone_applied(self, tmp_csv):
        """CSV has no timezone column, so default should be used."""
        events = parse_csv(tmp_csv)
        assert events[0].timezone == "America/New_York"

    def test_valid_events_pass_validation(self, tmp_csv):
        events = parse_csv(tmp_csv)
        for event in events:
            assert event.validate() == [], f"Event '{event.title}' has unexpected errors"


# =========================================================================== #
#  Edge cases & error handling
# =========================================================================== #

class TestCsvParserEdgeCases:

    def test_missing_file_raises_error(self):
        with pytest.raises(FileNotFoundError):
            parse_csv("/nonexistent/path.csv")

    def test_empty_required_fields_still_parsed(self, tmp_csv_missing_fields):
        """Events with missing required fields should still be returned (with validation errors)."""
        events = parse_csv(tmp_csv_missing_fields)
        assert len(events) == 1
        assert len(events[0].validate()) == 6  # all 6 required fields missing

    def test_alternate_headers_mapped(self, tmp_csv_alt_headers):
        """Column names like 'Event Title' and 'Start Date' should map correctly."""
        events = parse_csv(tmp_csv_alt_headers)
        assert len(events) == 1
        assert events[0].custom_state == "Texas"
        assert events[0].custom_city == "Austin"

    def test_whitespace_in_values_stripped(self, tmp_path):
        csv_content = (
            'title,description,start_date,start_time,end_date,end_time\n'
            '"  Spaced Title  ","  desc  ","04/15/2026","18:30:00","04/15/2026","20:30:00"\n'
        )
        csv_file = tmp_path / "spaced.csv"
        csv_file.write_text(csv_content)
        events = parse_csv(csv_file)
        assert events[0].title == "Spaced Title"
        assert events[0].description == "desc"

    def test_custom_column_map(self, tmp_path):
        """Verify that a custom column map overrides the default."""
        csv_content = 'my_title,my_desc,sd,st,ed,et\n"Test","Desc","01/01/2026","09:00:00","01/01/2026","11:00:00"\n'
        csv_file = tmp_path / "custom.csv"
        csv_file.write_text(csv_content)

        custom_map = {
            "my_title": "title",
            "my_desc": "description",
            "sd": "start_date",
            "st": "start_time",
            "ed": "end_date",
            "et": "end_time",
        }
        events = parse_csv(csv_file, column_map=custom_map)
        assert len(events) == 1
        assert events[0].title == "Test"

    def test_bom_encoded_csv(self, tmp_path):
        """UTF-8 BOM encoded CSVs should parse correctly."""
        csv_content = '\ufefftitle,description,start_date,start_time,end_date,end_time\n"BOM Test","desc","01/01/2026","09:00:00","01/01/2026","11:00:00"\n'
        csv_file = tmp_path / "bom.csv"
        csv_file.write_text(csv_content, encoding="utf-8-sig")
        events = parse_csv(csv_file)
        assert events[0].title == "BOM Test"


# =========================================================================== #
#  _row_to_event unit tests
# =========================================================================== #

class TestRowToEvent:

    def test_basic_row_conversion(self):
        row = {
            "title": "Test Event",
            "description": "A description",
            "start_date": "03/01/2026",
            "start_time": "10:00:00",
            "end_date": "03/01/2026",
            "end_time": "12:00:00",
        }
        event = _row_to_event(row, DEFAULT_COLUMN_MAP)
        assert event.title == "Test Event"
        assert event.start_date == "03/01/2026"

    def test_venue_id_parsed_as_int(self):
        row = {
            "title": "T", "description": "D",
            "start_date": "01/01/2026", "start_time": "09:00:00",
            "end_date": "01/01/2026", "end_time": "11:00:00",
            "venue_id": "518716",
        }
        event = _row_to_event(row, DEFAULT_COLUMN_MAP)
        assert event.venue.venue_id == 518716

    def test_empty_venue_id_is_none(self):
        row = {
            "title": "T", "description": "D",
            "start_date": "01/01/2026", "start_time": "09:00:00",
            "end_date": "01/01/2026", "end_time": "11:00:00",
            "venue_id": "",
        }
        event = _row_to_event(row, DEFAULT_COLUMN_MAP)
        assert event.venue.venue_id is None

    def test_unmapped_columns_ignored(self):
        row = {
            "title": "T", "description": "D",
            "start_date": "01/01/2026", "start_time": "09:00:00",
            "end_date": "01/01/2026", "end_time": "11:00:00",
            "random_garbage_column": "should be ignored",
        }
        event = _row_to_event(row, DEFAULT_COLUMN_MAP)
        assert event.title == "T"  # should not blow up
