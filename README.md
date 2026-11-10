# RoboLoCo Attendance Tracker

**Live App → [robolocoattendance.streamlit.app](https://robolocoattendance.streamlit.app)**

---

## Overview

RoboLoCo (FIRST Robotics Competition Team 5338) holds meetings several times a week across four subteams — Executive, Loco, Mechanical, and Software. For a long time, our team secretary was manually recording attendance for 70+ members at every meeting in a spreadsheet by hand. As the team grew, this became unsustainable, especially during build season when meetings happen daily.

This app fully automates that process. It supports multiple check-in methods, computes statistics dynamically, visualizes trends, and syncs to Google Sheets — reducing attendance tracking to a matter of seconds per meeting.

---

## Features

### Dashboard
Real-time attendance overview including latest meeting percentage, overall team average, and how many members are below the 70% threshold. Displays a week-over-week trend chart and an action center listing members who need follow-up. Automatic alerts fire when attendance drops or a member falls below threshold.

### Take Attendance
Manual check-in interface with a searchable checkbox grid of all members. Supports backdated entries, an optional meeting toggle (absences marked as `O` and excluded from percentage calculations), and writes directly to the master CSV and Google Sheet on submission.

### Slack Sync
Paste a Slack message link and the app fetches all emoji reactions via the Slack API and maps them to subteams:
- 🛠 `hammer_and_wrench` / `wrench` → Mechanical (written "Build" in some messages)
- 💻 `computer` → Software ("Programming")
- 🎨 `art` → Loco
- 💼 `briefcase` → Executive ("Leadership")
- 📝 `memo` / `pencil` → Mentors
- 🏫 `school` → Coaches — recorded like any subteam, but exempt from the 70% threshold and excluded from team-level stats
- 📚 `books` → excused for that meeting (college apps): recorded `O`, so it doesn't count against them
- 👎 thumbs-down variants → Won't attend (still `A`)

Matches Slack display names against the roster and warns about any unresolved names.

Before saving, a **double-check** panel compares the message against what the app is about to write: the
date named in the message vs. the date picker (with a one-click fix, and saving gated behind an
acknowledgement when they disagree), whether that date already has attendance that would be replaced, and
any reactor who isn't on the roster. Only dates are compared; meeting times like "3-7pm" are ignored and
never mistaken for a date.

Messages don't always invite the whole team. The app reads the emoji in the message text to detect which subteams were asked (`:hammer_and_wrench:` / 🛠 glyphs both work) and shows them pre-selected — the text rather than the reactions, so a group that was invited but hasn't reacted yet isn't mistaken for uninvited; members of a subteam that was never invited are recorded as `O` rather than `A`, so a meeting they weren't asked to doesn't dent their percentage. The selection is editable before saving.

### Member Insights
Per-member profile with overall attendance percentage, last attended date, and consecutive meetings missed. Includes an individual cumulative attendance trend chart over time.

### Edit Attendance
Spreadsheet-style data editor for correcting any past record. Supports all five status codes with direct cell editing and one-click save back to the master CSV.

### Google Drive Sync
One-click export of the full attendance dataset to a shared Google Sheet. Recalculates all percentages before upload. Blank cells are left blank rather than being filled with `O`.

### Generate QR Codes
Generates a unique QR code for every member (encoding `ROBOLOCO:{Full Name}`). Displayed in a searchable, filterable grid with individual PNG download per member.

### QR Check-In
Live camera-based QR code scanner built on OpenCV. Members hold up their QR code and are added to a checked-in list in real time. Supports optional meeting mode and submits batch attendance on confirmation.

### Settings
Shows the active Google Sheet and the service-account email, with from-scratch instructions for setting up a new season's spreadsheet. An admin login lets you test a new sheet and switch the app to it (full instructions are on the Settings page itself). Resolution order: `data/settings.json` (set on the page) → `SHEET_ID` in Streamlit secrets → built-in default.

### Saturday double sessions
Saturday meetings count twice: every entry page writes the same status to `MM/DD/YY` and `MM/DD/YY.1`. Date columns are always kept in chronological order in the sheet.

---

## Check-In / Check-Out (rotating code)

A separate, independent record of who was **actually in the room**, for checking the
Slack RSVPs against reality. It writes to its own tabs and never touches the attendance
tab; the two are only ever compared side by side, read-only.

**How it works.** A static QR code at the door opens the check-in page. That link on its
own does nothing — the student also has to type a 4-digit code that is only visible on
the kiosk screen in the shop and changes every 30 seconds. Forwarding the link to a friend
at home gets them nowhere.

The code is derived on the server and never sent to the browser as a secret:

```
code = HMAC(CHECKIN_SECRET, "<meeting_id>|<window>|<direction>") -> 4 digits
window = floor(server_epoch / ROTATION_SECONDS)
```

Check-in and check-out have different codes, so a check-out code can't be used to sign in
(or the reverse). The previous window is also accepted, so slow typers aren't punished.

**Pages**

| Page | Who | What |
|---|---|---|
| Check-In Kiosk | mentor | PIN-gated. Start/End meeting, both live codes, countdown, live "Signed in: N" |
| Check In / Out | student | Pick your name, type the code, check in or out |
| Check-In Admin | mentor | Flagged rows, who forgot to check out, manual fix-ups, and said-vs-showed |

**Meetings are opened and closed by hand** on the kiosk. Check-in only works while one is
open, and ending it auto-checks-out anyone still signed in, marking them `auto_checked_out`
so you can see who forgot. (Streamlit Cloud has no scheduler, so closing the meeting is what
triggers it — there is no timer.)

**Tabs it creates** in the same spreadsheet, on first use:

- `Meetings` — `meeting_id | date | label | opened_at | closed_at | opened_by`
- `SessionLog` — `meeting_id | date | full_name | check_in_at | check_out_at | duration_min | auto_checked_out | device_id | flagged | flag_reason`

Writes are appends and single-cell updates, never the clear-and-rewrite the attendance tab
uses, so many phones checking in at once can't clobber each other.

**Staying inside the API quota.** Google allows roughly 60 reads/minute per user, shared by
everyone using the app. The kiosk refreshes its codes every second, so that part makes **no**
API calls at all — the code is computed locally from the secret. Only the "Signed in: N"
headcount reads the sheet, every `SIGNED_IN_REFRESH_SECONDS` (default 20), and the spreadsheet
and tab handles are cached rather than re-opened per call. That is about 3 reads/minute for an
idle kiosk. Rate-limited calls are retried with backoff, and if one still fails, students see
"the sheet is busy, try again in a few seconds" rather than a traceback.

### Setup

Add to the app's **Secrets** on Streamlit Cloud:

```toml
CHECKIN_SECRET = "a-long-random-string-nobody-can-guess"
kiosk_pin = "1234"
ROTATION_SECONDS = 30
```

`CHECKIN_SECRET` is the only one that really matters. **Until it is set the app uses a
default that is published in this repo**, so anyone who can read the source can generate
valid codes — the kiosk shows a red warning while that is the case. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`kiosk_pin` defaults to `5338` and only needs to stop a student opening the code screen at
home. The Check-In Admin page uses the same login as Settings.

### Running the kiosk

Open **Check-In Kiosk** on the shop laptop or TV, enter the PIN, click **Start meeting**,
and put it full screen (F11). It refreshes itself; leave it alone for the meeting.

The page asks the browser for a Wake Lock, but **set the laptop's display to never sleep**
as well — that's the part that reliably works.

### The honest limits

The rotating code proves someone is **in the room**. It does not prove **who they are**.
A student in the shop can check in an absent friend by picking their name. The device
cookie catches the lazy version of that — one phone checking in several students gets
those rows flagged for a human to look at — but two students with two phones will get
through. Without logins that is the ceiling, and it is worth saying out loud before
anyone treats this log as proof of anything.

---

## Attendance Codes

| Code | Meaning | Counts Toward % |
|------|---------|----------------|
| `P` | Present | Yes |
| `L` | Late | Yes |
| `A` | Absent | No (counted in denominator) |
| `Z` | Excused absence | No (counted in denominator) |
| `O` | Opted out / optional | Ignored entirely |

---

## Tech Stack

| Tool | Purpose |
|------|---------|
| [Streamlit](https://streamlit.io) | Web app framework |
| [Pandas](https://pandas.pydata.org) | Data processing and aggregation |
| [Plotly](https://plotly.com) | Interactive charts |
| [gspread](https://gspread.readthedocs.io) | Google Sheets API integration |
| [Google Auth](https://google-auth.readthedocs.io) | Service account authentication |
| [Slack SDK](https://slack.dev/python-slack-sdk/) | Slack API integration |
| [OpenCV](https://opencv.org) | QR code scanning via camera |
| [qrcode](https://pypi.org/project/qrcode/) | QR code generation |
| [Pillow](https://pillow.readthedocs.io) | Image handling |
| [openpyxl](https://openpyxl.readthedocs.io) | Excel file support |

---

## Folder Structure

```
RoboLoCo_Attendance_App/
├── app.py                    # Entry point and page routing
├── data_loader.py            # CSV read/write and aggregation helpers
├── slack_integration.py      # Slack API logic
├── model.py                  # Attendance prediction (in development)
├── pages/
│   ├── 1_dashboard.py
│   ├── 2_take_attendance.py
│   ├── 3_slack_sync.py
│   ├── 4_member_insights.py
│   ├── 5_edit_specific_date.py
│   ├── 6_google_drive_sync.py
│   ├── 7_generate_qr.py
│   └── 8_qr_checkin.py
├── data/
│   ├── attendance.csv        # Master attendance dataset
│   └── service_account.json # GCP credentials (gitignored)
├── requirements.txt
└── .streamlit/
    └── secrets.toml          # Local secrets (gitignored)
```

---

## Local Setup

**1. Clone the repository**
```bash
git clone https://github.com/aghosal1317/RoboLoCo_Attendance_App.git
cd RoboLoCo_Attendance_App
```

**2. Install dependencies**
```bash
pip3 install -r requirements.txt
```

**3. Configure secrets**

Create `.streamlit/secrets.toml` — this file is gitignored and must never be committed:
```toml
SLACK_TOKEN = "xoxb-your-slack-token"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-key-id"
private_key = """-----BEGIN PRIVATE KEY-----
your key here
-----END PRIVATE KEY-----"""
client_email = "your@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-account"
universe_domain = "googleapis.com"
```

The service account must have access to the Google Sheet used for sync. Share the sheet with the `client_email` address.

**4. Run the app**
```bash
streamlit run app.py
```

---

## Deployment

Deployed on Streamlit Community Cloud with automatic redeployment on every push to `main`. Secrets are stored securely via Streamlit's secrets management and are never exposed in the repository.

**Live at: [robolocoattendance.streamlit.app](https://robolocoattendance.streamlit.app)**

---

## Roadmap

- [x] CSV parsing and dynamic percentage calculation
- [x] Dashboard with trend charts and low-attendance alerts
- [x] Manual attendance entry with optional meeting support
- [x] Member insights with individual trend charts
- [x] Edit attendance records
- [x] Google Sheets sync
- [x] Slack reaction-based attendance sync
- [x] QR code generation per member
- [x] Live QR code camera check-in
- [ ] Automated weekly summary report to coaches
- [ ] Attendance prediction model

---

## About

Built by Aneesh Ghosal, member of FRC Team 5338 — RoboLoCo.

---

## Running the tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

The suite needs no network or credentials: the Google Sheet is replaced by an in-memory fake, and page tests drive the real Streamlit pages through `streamlit.testing.AppTest`.
