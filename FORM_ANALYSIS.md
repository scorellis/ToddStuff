# Sip & Script Form Analysis — Key Findings

## 🎉 Good News: This Is Very Automatable

The form at `https://sipandscript.com/allevents/squad/add` is powered by
**The Events Calendar Community Events** (v6.15.15), a well-known WordPress plugin
by Modern Tribe / StellarWP. The form is a standard `POST` with `multipart/form-data` —
no JavaScript-dependent submission, no AJAX wizardry, no reCAPTCHA on the form itself.

**The reCAPTCHA is only on the public-facing site (mailing list popups, etc.),
NOT on this authenticated form.**

## Strategy: Selenium for Login → Requests for Form Submission

Since you're already logged in when you reach this page, the workflow is:

1. **Login once** via Selenium (handle Google OAuth interactively)
2. **Capture session cookies** (WordPress auth cookies)
3. **Reuse cookies with `requests`** for all subsequent form POSTs
4. No need to drive a browser for every submission!

## Form Endpoint

- **URL:** `https://sipandscript.com/allevents/squad/add`
- **Method:** `POST`
- **Encoding:** `multipart/form-data`
- **Action:** Posts to itself (no explicit action attribute = same URL)

## Required Hidden Fields (must be fetched fresh each submission)

| Field | Example Value | Notes |
|-------|---------------|-------|
| `post_ID` | `524553` | Pre-assigned post ID, changes each page load |
| `_wpnonce` | `d0a24d3d3c` | WordPress security nonce, EXPIRES — must fetch fresh |
| `_wp_http_referer` | `/allevents/squad/add` | Static |
| `tribe-events-virtual[virtual-nonce]` | `79362addae` | Virtual event nonce |
| `tribe-events-status[nonce]` | `a06c4bb579` | Status nonce |
| `tribe-tickets-post-settings` | `56436247f1` | Tickets nonce |

## Core Event Fields (from your CSV)

| Field Name | Type | Required | Notes |
|------------|------|----------|-------|
| `post_title` | text | ✅ Yes | Event title |
| `tcepostcontent` | textarea | ✅ Yes | Event description (HTML OK) |
| `EventStartDate` | text | Yes | Format: `MM/DD/YYYY` (datepicker_format=2) |
| `EventStartTime` | text | Yes | Format: `HH:MM:SS` (e.g., `18:00:00`) |
| `EventEndDate` | text | Yes | Format: `MM/DD/YYYY` |
| `EventEndTime` | text | Yes | Format: `HH:MM:SS` |
| `EventTimezone` | select | Yes | Default: `America/New_York` |
| `EventAllDay` | checkbox | No | Value: `yes` if checked |

## Venue Fields

| Field Name | Type | Notes |
|------------|------|-------|
| `venue[VenueID][]` | select | Use existing venue ID (e.g., `518716` for "Aged in Oak") |
| `venue[Venue][]` | text | OR create new venue name |
| `venue[Address][]` | text | Street address |
| `venue[City][]` | text | City |
| `venue[State][]` | select | State dropdown |
| `venue[Province][]` | text | Province (non-US) |
| `venue[Zip][]` | text | ZIP code |
| `venue[Country][]` | select | Country |
| `venue[Phone][]` | text | Phone |
| `venue[URL][]` | text | Website URL |

## Organizer Fields

| Field Name | Type | Notes |
|------------|------|-------|
| `organizer[OrganizerID][]` | select | Use existing organizer ID |
| `organizer[Organizer][]` | text | OR create new organizer |
| `organizer[Phone][]` | text | Phone |
| `organizer[Website][]` | url | Website |
| `organizer[Email][]` | text | Email |

## Additional / Custom Fields

| Field Name | Label | Type |
|------------|-------|------|
| `EventURL` | External Link | text |
| `_ecp_custom_3` | Ticket Max Capacity | text |
| `_ecp_custom_5` | State | dropdown (all 50 US states) |
| `_ecp_custom_10` | City | text |

## Ticket Fields (if applicable)

| Field Name | Type | Notes |
|------------|------|-------|
| `ticket_description` | textarea | Ticket description |
| `ticket_price` | text | Price |
| `ticket_start_date` | text | Sale start date |
| `ticket_end_date` | text | Sale end date |
| `ticket_start_time` | text | Sale start time |
| `ticket_end_time` | text | Sale end time |
| `ticket_sku` | text | SKU |
| `tribe-ticket[capacity]` | text | Max tickets |
| `tribe-ticket[mode]` | radio | Capacity mode |
| `ticket_provider` | hidden | `Tribe__Tickets_Plus__Commerce__WooCommerce__Main` |

## Submit

| Field Name | Value |
|------------|-------|
| `community-event` | `Submit Event` |

## Critical Implementation Notes

1. **Nonces expire** — you MUST `GET` the form page first to extract fresh nonces
   before each `POST`. This is a two-step process: fetch page → parse nonces → post.

2. **Venue/Organizer IDs** — If you always use the same venues, you can hardcode the
   IDs from the dropdown. Otherwise, use `-1` + fill in the name/address fields to
   create new ones.

3. **Categories/Tags** — These use AJAX search (`data-source="search_terms"`), so
   you'll need to either know the term IDs or skip them.

4. **Date format** — The `data-datepicker_format="2"` means `MM/DD/YYYY`.

5. **The form posts to itself** — No separate API endpoint, just POST to the same
   URL with all the form data.
