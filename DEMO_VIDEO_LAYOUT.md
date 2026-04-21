# Demo Video Script — RoboLoCo Attendance Tracker
**Target length:** 2.5 – 3 minutes  
**Format:** Screen recording with voiceover

---

## HOOK — 0:00 to 0:15
**Screen:** Nothing. Black screen or your face on camera.

> "Our robotics team has over 70 members. We meet multiple times a week.
> And for years, someone had to sit there with a spreadsheet and take attendance
> by hand at every single meeting. I built something to fix that."

**Cut to:** App loading on screen.

---

## DASHBOARD — 0:15 to 0:45
**Screen:** Dashboard page, fully loaded with real data.

> "This is what coaches see the moment they open it."

Slowly mouse over each metric as you say it:

> "Latest meeting attendance. Team average. Members below 70%.
> And a trend chart showing whether we're improving or declining week over week."

Scroll down to the alerts and action center:

> "If someone drops below threshold, the app flags it automatically — and tells you
> exactly who it is. No digging through spreadsheets."

---

## TAKING ATTENDANCE — 0:45 to 1:45

### Manual — 0:45 to 1:05
**Screen:** Take Attendance page.

> "The simplest way to take attendance — a checkbox grid for every member.
> You can search by name, pick the date, and mark it as optional so absences
> don't count against people."

Type a name in the search bar. Check a few boxes. Don't submit.

---

### QR Code — 1:05 to 1:25
**Screen:** Generate QR Codes page, then QR Check-In page.

> "Every member has their own QR code. They can screenshot it, put it in their
> phone camera roll, whatever. When they walk into the room—"

Switch to QR Check-In. Hold up or scan a code.

> "—one scan and they're in. The checked-in list updates live."

---

### Slack Sync — 1:25 to 1:45
**Screen:** Slack Sync page.

> "We use Slack for everything. Before meetings, members react to a message
> with their subteam emoji — a hammer for Mech, a laptop for Software.
> Paste the message link here, and the app reads every reaction and fills in
> attendance automatically. No manual entry at all."

Paste a link (or show the result already loaded).

---

## MEMBER INSIGHTS — 1:45 to 2:10
**Screen:** Member Insights page. Search for a real member.

> "Coaches can pull up any member individually."

Point to each stat:

> "Their attendance percentage. Last meeting they came to. And how many
> meetings in a row they've missed. That last one matters — it catches people
> who are quietly disengaging before it becomes a bigger problem."

Hover over the trend line chart.

> "This shows their consistency over time, not just a single number."

---

## UNDER THE HOOD — 2:10 to 2:30
**Screen:** Stay on app, or briefly flash the GitHub repo / a code snippet.

> "This is built in Python — Streamlit for the interface, Google Sheets API
> for cloud sync, Slack API for the emoji parsing, and OpenCV for the QR scanner.
> It's deployed on Streamlit Cloud and auto-updates when I push changes.
> Credentials are stored securely — nothing sensitive is in the repo."

Brief pause.

> "I built this because our team needed it. It's been running at every meeting
> since I launched it."

---

## CLOSE — 2:30 to 2:45
**Screen:** Back to the dashboard with real data visible.

> "Attendance tracking that used to take 10 minutes now takes seconds.
> Coaches have visibility they never had before. And the secretary doesn't have
> to do any of it by hand anymore."

Fade out.

---

## PRODUCTION NOTES

**Recording**
- Mac screen record: `Cmd + Shift + 5` → Record Selected Portion
- Zoom browser to 125% before recording so text is legible (`Cmd + =`)
- Use real member data — real names and real percentages read as legitimate

**Editing**
- Cut every pause longer than 1 second
- Add subtle zoom-ins when pointing at specific numbers (CapCut / iMovie both do this)
- Background music: lo-fi or light instrumental, well under the voiceover

**Thumbnail**
- Left side: old messy spreadsheet screenshot
- Right side: your clean dashboard
- Text overlay: "I automated this"
