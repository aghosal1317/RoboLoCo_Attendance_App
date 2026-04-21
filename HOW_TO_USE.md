# RoboLoCo Attendance Tracker — How to Use
### FRC Team 5338 | robolocoattendance.streamlit.app

---

## Getting Started

Open the app at **robolocoattendance.streamlit.app** on any phone, tablet, or computer. No login required.

The sidebar on the left lists every page. Click any page name to navigate to it. On mobile, tap the **>** arrow in the top-left corner to open the sidebar.

---

## Page 1 — Dashboard

**What it is:** The home screen. Shows the health of team attendance at a glance.

**What you'll see:**

- **Attendance on [date]** — the percentage of members who came to the most recent meeting
- **Overall Average** — the team's attendance percentage across the entire season, with a delta showing how this week compared to last week
- **Members Below 70%** — a count of members who are under the threshold

**Alerts:**
- A yellow warning appears if any member is below 70%
- A red alert appears if attendance dropped compared to last week

**Weekly Trend chart:**
Shows attendance percentage plotted week by week across the season. Hover over any point to see the exact number.

**Action Center:**
A collapsible panel at the bottom listing every member currently below 70%, sorted from lowest to highest. Click the arrow to expand it. If everyone is above 70%, it shows a green success message instead.

**When to use it:** Check this at the start of every meeting and before presenting to coaches.

---

## Page 2 — Take Attendance

**What it is:** The manual check-in page. Use this to record who came to a meeting by checking off names.

**Step by step:**

1. **Set the meeting type** — toggle "Optional Meeting" on if this meeting is optional (e.g. a weekend work session). When optional, members who don't show up get an **O** code instead of **A**, meaning their attendance percentage is not penalized.

2. **Set the date** — defaults to today. Click the date field to change it if you're entering attendance for a past meeting.

3. **Search for a member** — type any part of a name in the search box to filter the list. Leave it blank to see everyone.

4. **Check off who attended** — members are displayed in a 3-column grid. Check the box next to everyone who showed up.

5. **Click "Submit Attendance"** — the app saves to the local file and syncs to Google Sheets automatically. A green success message confirms it worked.

**Important:** Submitting always pulls the latest data from Google Sheets first before writing, so you won't accidentally overwrite changes someone else made.

---

## Page 3 — Slack Sync

**What it is:** Automatically reads emoji reactions from a Slack message and fills in attendance based on who reacted.

**How it works:**  
Before a meeting, post a message in your team Slack channel and ask members to react with their subteam emoji:
- 🔨 `:hammer_and_wrench:` → Mechanical
- 💻 `:computer:` → Software
- 🎨 `:art:` → Loco
- 💼 `:briefcase:` → Executive
- 👎 Any thumbs-down variant → Won't attend

**Step by step:**

1. **Copy the Slack message link** — in Slack, hover over the message → click the three dots (···) → "Copy link"

2. **Paste the link** into the input field on this page

3. **Click the sync button** — the app fetches all reactions from the Slack API and maps them to subteams

4. **Review the results** — you'll see a breakdown of who reacted with what, organized by subteam. Any names that couldn't be matched to the roster will be flagged with a warning.

5. **Submit** — saves the attendance the same way as the manual page

**Note:** The Slack bot token must be active for this to work. If you see an error about the token, check that `SLACK_TOKEN` is set correctly in `.streamlit/secrets.toml`.

---

## Page 4 — Member Insights

**What it is:** A deep-dive profile for any individual member.

**Step by step:**

1. **Search for a member** — type their name in the search box

2. **Select them** from the dropdown that appears

3. **Read their stats:**
   - **% Meetings Attended** — calculated correctly: P and L count as present, A and Z count against them, O is ignored entirely
   - **Last Attended** — the date of their most recent meeting
   - **Consecutive Missed** — how many meetings in a row they've missed going into today. A non-zero number here is a flag worth acting on.

4. **Read the chart** — the cumulative attendance trend shows how their percentage has moved over the season. A line going down means their attendance is getting worse over time. A flat or rising line means they're consistent.

**When to use it:** When a coach asks about a specific member, or when you're preparing for a check-in conversation with someone who's been absent.

---

## Page 5 — Attendance Predictions (Beta)

**What it is:** A machine learning model that uses historical attendance patterns to predict who will show up to the next meeting.

**How the model works:**  
The app trains three models (Logistic Regression, Random Forest, Gradient Boosting) on all past attendance records and picks the most accurate one. It looks at each member's last 3 meeting results, their rolling averages, their overall percentage, how many meetings in a row they've missed, and where we are in the season.

**What you'll see:**

- **Model Comparison table** — shows the cross-validation accuracy of all three models. The best one is starred and used for predictions.
- **Predicted to Attend / Predicted Absent / Predicted Attendance %** — summary metrics for the next meeting
- **Filter by subteam** — use the dropdown to narrow predictions to one subteam
- **Prediction table** — every member with their current attendance %, their predicted probability of attending (shown as a progress bar), and whether the model thinks they'll be there
- **Distribution chart** — shows how spread out the probabilities are across subteams
- **At-Risk Members** — a bar chart of everyone predicted to miss the next meeting, sorted from least likely to attend to most likely
- **Feature Importance chart** — shows which signals the model relied on most. The top two are almost always "Meeting # in Season" (attendance dips late-season) and "Consecutive Absences" (streaks predict streaks)

**Important:** This is a prediction tool, not a definitive answer. Use it to know who to follow up with before a meeting, not to make roster decisions.

---

## Page 6 — Edit Attendance

**What it is:** A direct spreadsheet editor for correcting any past attendance record.

**Step by step:**

1. **The table loads** showing all members and all meeting dates. Scroll right to see more dates.

2. **Click any cell** to edit it. Valid codes are:
   - `P` — Present
   - `A` — Absent
   - `L` — Late
   - `O` — Opted out / Optional (no effect on percentage)
   - `Z` — Excused absence (counted in denominator but not as present)

3. **Add or remove rows** using the buttons below the table if needed

4. **Click Save** — the app recalculates all percentages and saves to both the local file and Google Sheets

**Warning shown on save:** The app warns that Google Sheets may have been edited directly since your last load. If someone else was editing the sheet at the same time, the last save wins. Coordinate with your team to avoid conflicts.

**When to use it:** Correcting a misclick from Take Attendance, adding attendance for a meeting you forgot to record, or bulk-fixing a date that was entered wrong.

---

## Page 7 — Google Drive Sync

**What it is:** A one-click button to push the entire attendance dataset to the connected Google Sheet.

**Step by step:**

1. **Click "Sync to Google Drive"**

2. The app will:
   - Recalculate all attendance percentages
   - Fill any missing date columns with `O`
   - Clear the Google Sheet
   - Write the full updated dataset

3. A success message confirms the sync completed

**When to use it:**
- After making bulk edits to the local CSV directly
- If the Google Sheet got out of sync (e.g. someone edited it manually)
- At the end of the season to make sure coaches have a clean final copy

**Note:** This overwrites the entire Google Sheet. Any formatting or formulas you've added to the sheet directly will be lost.

---

## Page 8 — Generate QR Codes

**What it is:** Generates a unique, printable QR code for every member on the roster.

**Step by step:**

1. **Browse the grid** — QR codes are displayed 4 per row, each labeled with the member's name

2. **Search by name** — type in the search box to filter to a specific member

3. **Filter by subteam** — use the dropdown to show only one subteam's codes

4. **Download a QR code** — click the download button under any code to save it as a PNG. Members can screenshot it or save it to their camera roll.

**How members use their QR code:**
Members save the PNG to their phone. At check-in, they open the image and hold the screen up to the camera on the QR Check-In page. The app decodes it instantly.

**What's encoded in the QR code:**  
Each code encodes the string `ROBOLOCO:Full Name` (e.g. `ROBOLOCO:Eshan Nayak`). The QR Check-In page looks for this prefix to validate codes.

**Tip:** Print out a sheet of all QR codes at the start of the season and laminate them. Members who forget their phone can still check in.

---

## Page 9 — QR Check-In

**What it is:** A live camera scanner that checks members in by reading their QR codes in real time.

**Step by step:**

1. **Set the meeting type** — toggle "Optional Meeting" if applicable. Members not scanned will get `O` instead of `A`.

2. **Set the date** — defaults to today

3. **Click "Take Photo"** — this activates the camera. Point it at a member's QR code (on their phone or a printed sheet). The photo is taken and decoded automatically.

4. **Watch the checked-in list** — as each member is scanned, their name appears in the "Checked In" section below

5. **Remove a mis-scan** — expand "Remove a mis-scan" and select the name to undo an accidental scan

6. **Click "Submit Attendance"** (primary blue button at the bottom) — everyone on the checked-in list is marked `P`, everyone else is marked `A` or `O` depending on your optional meeting setting

**Tips for scanning:**
- Good lighting makes a huge difference — avoid scanning in dim rooms
- Hold the QR code steady and about 6–12 inches from the camera
- If it doesn't scan, try zooming in on the QR code image first before taking the photo

**When to use it:** At the door of a meeting room as members arrive, or for larger meetings where checking boxes one by one is too slow.

---

## Attendance Codes Reference

| Code | Name | Counts as Present | Counts in Denominator | Notes |
|------|------|:-----------------:|:---------------------:|-------|
| `P`  | Present | ✅ Yes | ✅ Yes | Standard attendance |
| `L`  | Late | ✅ Yes | ✅ Yes | Treated same as P for % |
| `A`  | Absent | ❌ No | ✅ Yes | Hurts percentage |
| `Z`  | Excused | ❌ No | ✅ Yes | Still counts against % |
| `O`  | Opted Out | ❌ No | ❌ No | Ignored completely |

**The 70% rule:** Members below 70% attendance are flagged across the Dashboard and Action Center. The threshold is fixed in the app — contact the developer to change it.

---

## FAQ

**Q: The app loaded but the data looks wrong or outdated.**  
A: The app tries Google Sheets first, then falls back to the local CSV if the connection fails. Go to Page 7 (Google Drive Sync) and re-sync to restore the connection.

**Q: I submitted attendance but I don't see it.**  
A: Try refreshing the page. Streamlit caches data for performance. If it still doesn't appear, check Page 6 (Edit Attendance) to confirm the column was written, then sync via Page 7.

**Q: A member's name didn't match during Slack Sync.**  
A: The name in Slack must match the name in the roster exactly (case-insensitive). Ask the member to update their Slack display name, or go to Page 6 and enter their attendance manually.

**Q: The QR scanner isn't working.**  
A: Make sure your browser has camera permission. Try Chrome or Safari. Make sure the QR code is well-lit and fills most of the camera frame.

**Q: Can two people take attendance at the same time?**  
A: Not recommended — the last save wins and will overwrite the other. Designate one person to take attendance per meeting.

---

*RoboLoCo Attendance Tracker · FRC Team 5338 · Built by Aneesh Ghosal*
