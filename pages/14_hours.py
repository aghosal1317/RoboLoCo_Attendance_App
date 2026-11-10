"""
Hours — the raw check-in/check-out log in a readable form.

Everything here is derived from the SessionLog tab: time per member per
meeting, totals per member, and the grand total. Independent of the P/A
attendance, which is only ever expected attendance.
"""
import pandas as pd
import streamlit as st

import session_log
from settings import check_admin_login

st.title("Hours")
st.caption(
    "Time actually spent at meetings, from check-in to check-out. Rebuilt into the "
    "**Hours** tab of the spreadsheet whenever a meeting is closed."
)

if not st.session_state.get("admin_authed"):
    with st.form("hours_login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log in"):
            if check_admin_login(username, password):
                st.session_state.admin_authed = True
                st.rerun()
            else:
                st.error("Incorrect username or password.")
    st.stop()

try:
    rows = session_log.hours_rows()
    totals = session_log.member_totals()
    grand = session_log.total_hours()
except Exception as error:
    st.error("Couldn't read the check-in log just now — wait a few seconds and reload.")
    st.caption(f"({type(error).__name__})")
    st.stop()

if rows.empty:
    st.info("Nobody has checked in yet, so there are no hours to show.")
    st.stop()

# ----------------------------
# Totals
# ----------------------------
still_open = int((rows["minutes"] == "").sum())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total hours", f"{grand['hours']:,.2f}")
m2.metric("Total minutes", f"{grand['minutes']:,}")
m3.metric("Sessions counted", grand["sessions"])
m4.metric("Members", int(totals["full_name"].nunique()))

if still_open:
    st.caption(
        f"{still_open} session(s) are still open (checked in, not yet out) and are "
        "excluded from every total until the meeting is closed."
    )

auto_closed = int(totals["auto_closed"].sum()) if "auto_closed" in totals else 0
if auto_closed:
    st.caption(
        f"{auto_closed} session(s) were auto-checked-out at the end of a meeting, so "
        "those durations are a floor rather than a measurement."
    )

st.divider()

# ----------------------------
# Per member
# ----------------------------
st.subheader("Total per member")

display = totals.rename(columns={
    "full_name": "Member", "meetings": "Meetings", "minutes": "Minutes",
    "hours": "Hours", "still_open": "Still open", "auto_closed": "Auto checked out",
})
st.dataframe(display, width="stretch", hide_index=True)

st.download_button(
    "Download totals as CSV",
    data=display.to_csv(index=False).encode(),
    file_name="hours_by_member.csv",
    mime="text/csv",
)

st.divider()

# ----------------------------
# Every session
# ----------------------------
st.subheader("Every check-in")

names = ["All members"] + sorted(rows["full_name"].unique())
picked = st.selectbox("Filter", names)
detail = rows if picked == "All members" else rows[rows["full_name"] == picked]

detail_display = detail.rename(columns={
    "full_name": "Member", "date": "Date", "check_in_at": "Checked in",
    "check_out_at": "Checked out", "minutes": "Minutes", "hours": "Hours",
    "auto_checked_out": "Auto checked out",
})[["Member", "Date", "Checked in", "Checked out", "Minutes", "Hours", "Auto checked out"]]

st.dataframe(detail_display, width="stretch", hide_index=True)

if picked != "All members":
    done = detail[detail["minutes"] != ""]
    minutes = int(done["minutes"].astype(int).sum()) if not done.empty else 0
    st.caption(f"**{picked}** — {minutes} minutes ({minutes / 60:.2f} hours) across "
               f"{len(done)} meeting(s).")

st.download_button(
    "Download every check-in as CSV",
    data=detail_display.to_csv(index=False).encode(),
    file_name="hours_detail.csv",
    mime="text/csv",
)

st.divider()

if st.button("Rebuild the Hours tab now"):
    try:
        written = session_log.rebuild_hours_tab()
        st.success(f"Rebuilt the Hours tab — {written} rows.")
    except Exception as error:
        st.error(f"Couldn't write the Hours tab: {type(error).__name__}")
st.caption("It rebuilds on its own whenever a meeting is closed; this is for a manual refresh.")
