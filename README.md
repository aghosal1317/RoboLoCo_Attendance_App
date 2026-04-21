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
- 🔨 `hammer_and_wrench` → Mechanical
- 💻 `computer` → Software
- 🎨 `art` → Loco
- 💼 `briefcase` → Executive
- 👎 thumbs-down variants → Won't attend

Matches Slack display names against the roster and warns about any unresolved names.

### Member Insights
Per-member profile with overall attendance percentage, last attended date, and consecutive meetings missed. Includes an individual cumulative attendance trend chart over time.

### Edit Attendance
Spreadsheet-style data editor for correcting any past record. Supports all five status codes with direct cell editing and one-click save back to the master CSV.

### Google Drive Sync
One-click export of the full attendance dataset to a shared Google Sheet. Recalculates all percentages before upload and fills missing date columns with `O`.

### Generate QR Codes
Generates a unique QR code for every member (encoding `ROBOLOCO:{Full Name}`). Displayed in a searchable, filterable grid with individual PNG download per member.

### QR Check-In
Live camera-based QR code scanner built on OpenCV. Members hold up their QR code and are added to a checked-in list in real time. Supports optional meeting mode and submits batch attendance on confirmation.

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
