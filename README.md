# RoboLoCo Attendance Tracker

**Live App → [robolocoattendance.streamlit.app](https://robolocoattendance.streamlit.app)**

---

## Overview

RoboLoCo (FIRST Robotics Competition Team 5338) holds meetings several times a week across four subteams - Executive, Loco, Mechanical, and Software. For a long time, our team secretary was manually recording attendance for every member at every meeting in a spreadsheet by hand. As the team grew, this became increasingly time-consuming and error-prone.

I built this tool to fully automate that process. The app ingests our master attendance CSV, computes statistics dynamically, visualizes trends across subteams and months, and will soon sync attendance directly from Slack - where members already mark their presence by reacting to a message. The goal was to reduce the administrative burden on our secretary and give leads and mentors real-time visibility into team engagement.

---

## Features

- **Dashboard** — real-time attendance overview with weekly trend charts and automated low-attendance alerts
- **Member Insights** — per-member attendance percentage, last attended date, subteam rank, and individual trend chart
- **Subteam Analytics** — average attendance broken down by subteam with month-over-month comparisons
- **Google Sheets Sync** — one-click export of the full attendance dataset to a shared Google Sheet, with automatic percentage recalculation
- **Manual Attendance Entry** — backup check-in interface with per-member checkboxes and CSV write-back
- **Slack Sync** *(in development)* — will automatically pull attendance from Slack message reactions, eliminating manual data entry entirely
- **Reports** — downloadable CSV reports for record-keeping

---

## Motivation

Our secretary was spending significant time each week manually tracking who attended each meeting and calculating attendance percentages across 70+ members. This was not a sustainable workflow, especially during the competitive build season when meetings occur daily.

By building a centralized tool that reads from a single source of truth (our master CSV), recalculates statistics dynamically, and will eventually pull directly from Slack reactions, I aimed to reduce that overhead to near zero. Captains and mentors can now check attendance trends at a glance rather than waiting for a manual update.

---

## Tech Stack

| Tool | Purpose |
|------|---------|
| [Streamlit](https://streamlit.io) | Web app framework |
| [Pandas](https://pandas.pydata.org) | Data processing and aggregation |
| [Plotly](https://plotly.com) | Interactive charts |
| [gspread](https://gspread.readthedocs.io) | Google Sheets API integration |
| [Google Auth](https://google-auth.readthedocs.io) | Service account authentication |
| [Slack SDK](https://slack.dev/python-slack-sdk/) | Slack API integration *(in development)* |

---

## Folder Structure

```
attendance-app/
├── app.py                    # entry point and page routing
├── data_loader.py            # CSV read/write and aggregation helpers
├── slack_integration.py      # Slack API logic
├── model.py                  # attendance prediction
├── pages/
│   ├── 1_dashboard.py
│   ├── 2_take_attendance.py
│   ├── 3_slack_sync.py
│   ├── 4_member_insights.py
│   └── 5_reports.py
├── data/
│   └── attendance.csv        # master attendance dataset
├── requirements.txt
└── .streamlit/
    └── secrets.toml          # local secrets (gitignored)
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
pip install -r requirements.txt
```

**3. Configure secrets**

Create `.streamlit/secrets.toml` — this file is gitignored and should never be committed:
```toml
SLACK_TOKEN = "xoxb-your-slack-token"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-key-id"
private_key = """-----BEGIN RSA PRIVATE KEY-----
your key here
-----END RSA PRIVATE KEY-----"""
client_email = "your@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
token_uri = "https://oauth2.googleapis.com/token"
```

**4. Run the app**
```bash
streamlit run app.py
```

---

## Deployment

The app is deployed on Streamlit Community Cloud and automatically redeploys on every push to `main`. Secrets (Google service account credentials and Slack token) are stored securely via Streamlit's secrets management and are never exposed in the repository.

**Live at: [robolocoattendance.streamlit.app](https://robolocoattendance.streamlit.app)**

---

## Attendance Codes

| Code | Meaning |
|------|---------|
| `P` | Present |
| `A` | Absent |
| `O` | Excused |

---

## Roadmap

- [x] CSV parsing and dynamic percentage calculation
- [x] Dashboard with trend charts and alerts
- [x] Member insights page
- [x] Google Sheets sync
- [ ] Slack reaction-based attendance sync
- [ ] Automated weekly summary report
- [ ] Attendance prediction model

---

## About

Built by Aneesh Ghosal, member of FRC Team 5338 — RoboLoCo.
