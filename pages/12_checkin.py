"""
Student-facing check-in / check-out.

This is what the static QR code at the door opens. The link alone is useless:
you also need the 4-digit code showing on the kiosk screen in the shop.
"""
import streamlit as st

import session_log
from data_loader import load_data
from device_id import get_device_id
from rotating_code import verify_code

st.title("Check In / Check Out")

meeting = session_log.active_meeting()
if meeting is None:
    st.info("No meeting is open right now. Check-in opens when a mentor starts the meeting.")
    st.stop()

st.caption(
    f"Meeting on **{meeting['date']}**"
    + (f" — {meeting['label']}" if meeting.get("label") else "")
)


@st.cache_data(ttl=300, show_spinner=False)
def roster_names():
    """One roster, read from the attendance tab — no second list to maintain."""
    df = load_data()
    return sorted(df["Full Name"].dropna().astype(str).str.strip().unique())


names = roster_names()
signed_in = {n.strip().lower() for n in session_log.open_sessions(meeting["meeting_id"])}

name = st.selectbox(
    "Your name",
    options=[""] + names,
    format_func=lambda n: "Start typing your name…" if n == "" else n,
)

if not name:
    st.stop()

already_in = name.strip().lower() in signed_in
direction = "out" if already_in else "in"

if already_in:
    st.success("You're checked in. Enter the **check-out** code when you leave.")
else:
    st.info("Enter the **check-in** code from the screen in the shop.")

code = st.text_input("4-digit code from the screen", max_chars=4, placeholder="0000")

label = "Check out" if already_in else "Check in"
if st.button(label, type="primary", disabled=not code):
    if not verify_code(code, direction, meeting["meeting_id"]):
        st.error("Code expired, check the screen and try again.")
    elif already_in:
        result = session_log.check_out(meeting["meeting_id"], name)
        if result["ok"]:
            st.success(f"Checked out — see you next time, {name.split()[0]}.")
            st.balloons()
        elif result["reason"] == "already_checked_out":
            st.info("You're already checked out.")
        else:
            st.warning("You don't seem to be checked in for this meeting.")
    else:
        result = session_log.check_in(meeting["meeting_id"], name, device_id=get_device_id())
        if result["ok"]:
            st.success(f"Checked in — welcome, {name.split()[0]}.")
            st.caption("Come back and check out before you leave.")
        elif result["reason"] == "already_checked_in":
            st.info("You're already checked in for this meeting.")
        else:
            st.warning("Couldn't record that — find a mentor.")
