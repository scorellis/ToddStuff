# Test Manifest — Sip & Script Autoposter

## How to Run

```bash
# All tests (48 total)
python run_tests.py

# Unit tests only (42) — no network, no dependencies beyond stdlib
python run_tests.py --unit

# Integration tests only (6) — local mock server, needs `requests`
python run_tests.py --integ

# With pytest (if installed)
pytest -v
pytest -v -m "not integration"   # skip integration
```

## Test Suites

### Unit Tests (42)

| Suite | File | Tests | What It Covers |
|-------|------|-------|----------------|
| EventData Validation | test_models.py | 8 | Required fields, optional fields, defaults |
| Venue | test_models.py | 3 | ID-based, full details, default country |
| Organizer | test_models.py | 2 | ID-based, detail-based |
| AuthResult | test_models.py | 5 | Success, failure, manual intervention states |
| NonceExtractor | test_submitter.py | 3 | HTML parsing, edge cases |
| Form Data Builder | test_submitter.py | 10 | Nonces, fields, venue/organizer logic, all-day flag |
| Error Extraction | test_submitter.py | 3 | Error div parsing, HTML stripping |
| CSV Parser | test_csv_parser.py | 6 | Parsing, missing files, venue IDs, whitespace |
| Authenticator | test_authenticator.py | 3 | Strategy delegation, swap, cleanup |

### Integration Tests (6)

| Test | What It Proves |
|------|----------------|
| test_fetch_nonces_from_mock | GET form page → extract all 5 nonces correctly |
| test_successful_submit | Full flow: nonces → POST → redirect to success page |
| test_submit_without_auth_fails | Bad cookies → detected as auth failure |
| test_submit_empty_title_fails | Server-side validation → error extracted |
| test_batch_submit_three_events | 3 sequential submits all succeed |
| test_csv_to_submit_end_to_end | Parse CSV file → submit all events → all succeed |

## CI/CD

Tests run automatically via GitHub Actions on:
- Every push to `develop` or `main`
- Every pull request targeting `develop` or `main`

PRs cannot be merged unless all tests pass (branch protection rule).
