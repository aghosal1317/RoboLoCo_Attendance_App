# RoboLoCo Attendance Tracker
## FRC Team 5338 — Built by Aneesh Ghosal

---

### Why This Exists

70+ members. 4 subteams. Meetings every week, sometimes daily during build season.

Our team secretary was recording attendance by hand at every meeting and calculating percentages manually in a spreadsheet. It was slow, error-prone, and completely unsustainable. Nobody had visibility into who was falling behind until it was already too late.

**I built a web app to fix that.**

---

### What It Does

**robolocoattendance.streamlit.app** is a live attendance management system built specifically for Team 5338. It replaces the entire manual process with automated check-in, real-time analytics, and instant alerts — accessible from any phone or computer.

---

### Features

**Three ways to take attendance**
- Checkbox roll call with live name search
- QR code scanner — members hold up their unique code, camera checks them in instantly
- Slack sync — reads emoji reactions from a Slack message and auto-fills attendance by subteam

**Live Dashboard**
- Attendance percentage for the latest meeting
- Overall team average
- Week-over-week trend chart
- Automatic warning when a member drops below 70%
- Action center listing exactly who needs follow-up

**Member Profiles**
- Individual attendance history and trend line over time
- Last attended date
- Consecutive absences counter — catch members quietly slipping before it's a problem

**Data Tools**
- Edit any past record in a spreadsheet-style interface
- Auto-syncs to Google Sheets for coach access outside the app
- Five attendance codes: Present, Absent, Late, Opted Out, Excused

---

### Before vs. After

| Before | After |
|---|---|
| Hand-written roll call at every meeting | Three automated check-in options |
| Manual percentage calculations | Recalculated live on every submission |
| No trend visibility | Weekly trend chart on the dashboard |
| No early warning system | Automatic alerts below 70% threshold |
| Data on one person's laptop | Cloud-synced, accessible anywhere |

---

### Built With

Python · Streamlit · Google Sheets API · Slack API · OpenCV · Deployed on Streamlit Cloud

*Everything was designed, built, and maintained by a student member of Team 5338.*

---

**Live app:** robolocoattendance.streamlit.app · **Team:** FRC 5338 RoboLoCo
