# Sip & Script Autoposter — Sprint 1: Authentication Proof-of-Concept

## 🎯 Goal
Determine whether we can programmatically authenticate to sipandscript.com
(WordPress + Google OAuth + reCAPTCHA) and establish a session for future
automated class submissions.

## Architecture (SOLID Principles)

```
autoposter/
├── config/
│   ├── __init__.py
│   └── settings.py          # Single Responsibility: all config in one place
├── models/
│   ├── __init__.py
│   └── auth_result.py       # Data models (Open/Closed: extend, don't modify)
├── auth/
│   ├── __init__.py
│   ├── base.py              # Interface Segregation: abstract auth contract
│   ├── selenium_auth.py     # Strategy 1: Browser automation (Selenium)
│   └── session_auth.py      # Strategy 2: Direct HTTP (requests) — fallback
├── core/
│   ├── __init__.py
│   └── authenticator.py     # Dependency Inversion: depends on abstractions
├── utils/
│   ├── __init__.py
│   └── logger.py            # Logging utility
├── main.py                  # Entry point — Sprint 1: login test
├── requirements.txt
├── .env.example
└── README.md
```

## Key Design Decisions

| Concern | Decision | Why |
|---------|----------|-----|
| Google OAuth | Selenium (browser) | OAuth + reCAPTCHA can't be faked via HTTP |
| SOLID | Strategy pattern for auth | Swap Selenium ↔ requests without touching core |
| Security | `.env` file for credentials | Never hardcode secrets |
| Sprint scope | Login only | If this fails, we pivot to asking S&S for an API |

## Prerequisites

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

You also need **Google Chrome** installed on your machine.

## Setup

1. Copy `.env.example` → `.env`
2. Fill in your Google credentials
3. Run: `python main.py`

## What to Expect

### ✅ Success
The script opens Chrome, navigates to the WordPress login, clicks
"Login with Google," enters your credentials, and confirms you have
an authenticated session. You'll see cookies saved to `session_cookies.json`.

### ❌ Failure Scenarios & Next Steps
| Scenario | Likely Cause | Next Step |
|----------|-------------|-----------|
| Google blocks sign-in | "Unusual activity" / bot detection | Use `--manual` mode (see below) |
| reCAPTCHA challenge | Automated browser detected | Use `undetected-chromedriver` |
| 2FA prompt | Account has MFA enabled | Semi-manual: script waits for you |
| Site blocks automation entirely | WAF / Cloudflare | Contact Sip & Script for API access |

### Manual-Assist Mode
```bash
python main.py --manual
```
Opens browser, navigates to login, then **waits for you** to complete
Google sign-in manually. Once logged in, it captures the session cookies
for reuse in future automated runs.

## Sprint 2 (if Sprint 1 succeeds)
- CSV parser for class data
- Form submission automation
- Scheduling / cron support
# ToddStuff
