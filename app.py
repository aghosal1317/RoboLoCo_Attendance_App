import streamlit as st
from PIL import Image

logo = Image.open("assets/logo.jpg")

st.set_page_config(
    page_title="RoboLoCo Attendance",
    page_icon=logo,
    layout="wide",
)

st.logo("assets/logo.jpg")

pg = st.navigation([
    st.Page("home.py",                        title="Home"),
    st.Page("pages/1_dashboard.py",           title="Dashboard"),
    st.Page("pages/2_take_attendance.py",     title="Take Attendance"),
    st.Page("pages/3_slack_sync.py",          title="Slack Sync"),
    st.Page("pages/4_member_insights.py",     title="Member Insights"),
    st.Page("pages/5_predictions.py",         title="Predictions"),
    st.Page("pages/6_edit_specific_date.py",  title="Edit Attendance"),
    st.Page("pages/7_google_drive_sync.py",   title="Google Drive Sync"),
    st.Page("pages/8_generate_qr.py",         title="Generate QR Codes"),
    st.Page("pages/9_qr_checkin.py",          title="QR Check-In"),
])

pg.run()
