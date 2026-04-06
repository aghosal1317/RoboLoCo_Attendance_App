import streamlit as st
from PIL import Image

logo = Image.open("assets/logo.jpg")

st.set_page_config(
    page_title="Attendance Tracker",
    page_icon=logo,
    layout="wide"
)

st.logo("assets/logo.jpg")

col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.image("assets/logo.jpg", width=100)
with col_title:
    st.title("Attendance Tracker")
    st.markdown("Track, analyze, and manage team attendance. Use the sidebar to navigate.")

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    st.info("**📊 Dashboard**\nOverview of attendance trends, alerts, and members below 70%.")
    st.info("**✅ Take Attendance**\nMark members present or absent for today's meeting.")
    st.info("**✏️ Edit Attendance**\nDirect spreadsheet editor for correcting past records.")

with col2:
    st.info("**🔔 Slack Sync**\nImport attendance from Slack reaction emoji.")
    st.info("**📈 Member Insights**\nView attendance history and trends for individual members.")

with col3:
    st.info("**📄 Reports**\nWeekly summaries emailed to coaches and exec.")
    st.info("**☁️ Google Drive Sync**\nPush the attendance CSV up to a Google Sheet.")
    st.info("**🔲 Generate QR Codes**\nPrint or download unique QR codes for each member.")
    st.info("**📷 QR Check-In**\nMembers scan their QR code to mark themselves present.")