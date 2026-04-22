import streamlit as st

col_logo, col_text = st.columns([1, 5], vertical_alignment="center")
with col_logo:
    st.image("assets/logo.jpg", width=120)
with col_text:
    st.title("RoboLoCo Attendance Tracker")
    st.markdown("FRC Team 5338 · Select a page from the sidebar to get started.")

st.divider()

PAGES = [
    {
        "icon": "📊",
        "title": "Dashboard",
        "description": (
            "The main overview screen. Displays the latest meeting attendance percentage, "
            "overall team average, week-over-week trend chart, and a list of every member "
            "currently below the 70% threshold. Automatic alerts fire when attendance drops "
            "or a member needs follow-up."
        ),
        "use_when": "Check at the start of every meeting and before any coach presentation.",
    },
    {
        "icon": "✅",
        "title": "Take Attendance",
        "description": (
            "Manual check-in interface. Displays all roster members in a searchable checkbox "
            "grid. Supports optional meetings (absences marked O, no percentage penalty) and "
            "backdated entry. Submits directly to Google Sheets on save."
        ),
        "use_when": "Any meeting where QR scanning or Slack sync isn't being used.",
    },
    {
        "icon": "💬",
        "title": "Slack Sync",
        "description": (
            "Paste a Slack message link and the app reads all emoji reactions, mapping each "
            "reaction to a subteam (🔨 Mechanical, 💻 Software, 🎨 Loco, 💼 Executive). "
            "Unmatched names are flagged. Attendance is saved automatically on confirm."
        ),
        "use_when": "When members have reacted to a pre-meeting Slack message.",
    },
    {
        "icon": "📈",
        "title": "Member Insights",
        "description": (
            "Individual member profiles. Search by name to view attendance percentage, last "
            "attended date, consecutive meetings missed, and a cumulative attendance trend "
            "chart showing how their engagement has changed across the season."
        ),
        "use_when": "Before a check-in conversation with a member, or when a coach asks about someone.",
    },
    {
        "icon": "🤖",
        "title": "Predictions (Beta)",
        "description": (
            "Machine learning model trained on all historical attendance records. Compares "
            "Logistic Regression, Random Forest, and Gradient Boosting, then uses the best "
            "to predict who will attend the next meeting. Also shows at-risk members and "
            "which signals (streaks, rolling averages, season position) drive the model."
        ),
        "use_when": "Before a meeting to identify who to follow up with in advance.",
    },
    {
        "icon": "✏️",
        "title": "Edit Attendance",
        "description": (
            "Spreadsheet-style editor for any past meeting record. Click any cell to change "
            "the code (P, A, L, O, Z). Percentages are recalculated automatically on save. "
            "Syncs to Google Sheets on submission."
        ),
        "use_when": "Correcting a misclick, entering a forgotten meeting, or bulk-fixing a date.",
    },
    {
        "icon": "☁️",
        "title": "Google Drive Sync",
        "description": (
            "One-click export of the full attendance dataset to the connected Google Sheet. "
            "Recalculates all percentages, fills missing dates with O, clears the sheet, "
            "and uploads the entire dataset. Overwrites whatever is currently in the sheet."
        ),
        "use_when": "After direct CSV edits, or to ensure coaches have the latest copy.",
    },
    {
        "icon": "🔲",
        "title": "Generate QR Codes",
        "description": (
            "Generates a unique QR code for every member on the roster, encoding their name "
            "in the format ROBOLOCO:Full Name. Codes are displayed in a searchable, "
            "subteam-filterable grid with individual PNG download buttons."
        ),
        "use_when": "At the start of the season to distribute codes, or when a member needs a replacement.",
    },
    {
        "icon": "📷",
        "title": "QR Check-In",
        "description": (
            "Live camera-based scanner. Members hold up their QR code and the app detects "
            "and logs them instantly. Maintains a running checked-in list with mis-scan "
            "removal. Marks all non-scanned members absent (or opted out) on submission."
        ),
        "use_when": "At the door of a meeting for fast, hands-free check-in.",
    },
]

# Render in a 3-column grid of bordered cards
cols = st.columns(3)
for i, page in enumerate(PAGES):
    with cols[i % 3]:
        with st.container(border=True):
            st.markdown(f"### {page['title']}")
            st.markdown(page["description"])
            st.caption(f"**Use when:** {page['use_when']}")
