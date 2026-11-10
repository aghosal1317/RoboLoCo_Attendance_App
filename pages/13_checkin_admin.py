"""
Check-in admin — flagged records, people who forgot to check out, manual
fix-ups, and the comparison this whole system exists for: who said on Slack
they'd be here (P) versus who actually walked in.
"""
import pandas as pd
import streamlit as st

import session_log
from data_loader import load_data, get_date_columns, ATTENDED_CODES
from settings import check_admin_login

st.title("Check-In Admin")
st.caption(
    "The check-in log is independent of the P/A attendance. Nothing here changes "
    "the attendance tab — it's for comparing what people said against what happened."
)

# ----------------------------
# Admin gate (same credentials as Settings)
# ----------------------------
if not st.session_state.get("admin_authed"):
    with st.form("checkin_admin_login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log in"):
            if check_admin_login(username, password):
                st.session_state.admin_authed = True
                st.rerun()
            else:
                st.error("Incorrect username or password.")
    st.stop()

meetings = session_log.recent_meetings()
if meetings.empty:
    st.info("No meetings have been opened yet. Start one from the Kiosk page.")
    st.stop()


def meeting_label(mid):
    row = meetings[meetings["meeting_id"] == mid]
    if row.empty:
        return mid
    row = row.iloc[0]
    extra = f" — {row['label']}" if str(row.get("label", "")).strip() else ""
    state = "open" if not str(row.get("closed_at", "")).strip() else "closed"
    return f"{row['date']} ({state}){extra}"


selected = st.selectbox("Meeting", meetings["meeting_id"].tolist(), format_func=meeting_label)
sessions = session_log.sessions_for(selected)

if sessions.empty:
    st.info("Nobody checked in to this meeting.")
else:
    still_in = sessions[sessions["check_out_at"].astype(str).str.strip() == ""]
    auto = sessions[sessions["auto_checked_out"].astype(str).str.upper() == "TRUE"]
    flagged = sessions[sessions["flagged"].astype(str).str.upper() == "TRUE"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Checked in", len(sessions))
    m2.metric("Still signed in", len(still_in))
    m3.metric("Forgot to check out", len(auto))
    m4.metric("Flagged", len(flagged))

    if not flagged.empty:
        st.subheader("Flagged — same phone, more than one student")
        st.caption("Not blocked, just worth a look. A shared phone is the usual innocent explanation.")
        st.dataframe(flagged[["full_name", "check_in_at", "flag_reason"]],
                     width="stretch", hide_index=True)

    if not auto.empty:
        st.subheader("Forgot to check out")
        st.caption("Automatically checked out when the meeting ended, so their duration is a floor, not a fact.")
        st.dataframe(auto[["full_name", "check_in_at", "check_out_at", "duration_min"]],
                     width="stretch", hide_index=True)

    with st.expander(f"All check-ins ({len(sessions)})"):
        st.dataframe(
            sessions[["full_name", "check_in_at", "check_out_at", "duration_min",
                      "auto_checked_out", "flagged"]],
            width="stretch", hide_index=True,
        )

# ----------------------------
# Manual fix-ups
# ----------------------------
st.divider()
st.subheader("Manual check in / out")
st.caption("For a dead phone or a mis-scan. Doesn't need the rotating code.")


@st.cache_data(ttl=300, show_spinner=False)
def roster_names():
    return sorted(load_data()["Full Name"].dropna().astype(str).str.strip().unique())


name_col, in_col, out_col = st.columns([3, 1, 1])
with name_col:
    who = st.selectbox("Member", [""] + roster_names(),
                       format_func=lambda n: "Pick a member…" if n == "" else n)
with in_col:
    if st.button("Check in", disabled=not who):
        result = session_log.manual_override(selected, who, "in")
        st.session_state["_manual_msg"] = (
            f"Checked in {who}." if result["ok"] else "Already checked in.")
        st.rerun()
with out_col:
    if st.button("Check out", disabled=not who):
        result = session_log.manual_override(selected, who, "out")
        st.session_state["_manual_msg"] = (
            f"Checked out {who}." if result["ok"] else "Not checked in.")
        st.rerun()

if "_manual_msg" in st.session_state:
    st.success(st.session_state.pop("_manual_msg"))

# ----------------------------
# Said vs. showed
# ----------------------------
st.divider()
st.subheader("Said they'd come vs. actually showed")
st.caption(
    "Left: what Slack recorded as expected attendance (P or L) for that date. "
    "Right: who checked in at the door. Read-only — neither side is changed."
)

meeting_row = meetings[meetings["meeting_id"] == selected].iloc[0]
meeting_date = str(meeting_row["date"]).strip()

attendance = load_data()
date_cols = [c for c in get_date_columns(attendance)
             if c == meeting_date or c.startswith(f"{meeting_date}.")]

if not date_cols:
    st.info(f"No attendance column for {meeting_date} yet, so there's nothing to compare against.")
else:
    codes = attendance[date_cols[0]].fillna("").astype(str).str.strip()
    said_yes = set(attendance.loc[codes.isin(ATTENDED_CODES), "Full Name"].str.strip())
    showed = {n.strip() for n in sessions["full_name"]} if not sessions.empty else set()

    no_show = sorted(said_yes - showed)
    surprise = sorted(showed - said_yes)
    kept_word = sorted(said_yes & showed)

    c1, c2, c3 = st.columns(3)
    c1.metric("Said yes, didn't show", len(no_show))
    c2.metric("Showed, wasn't expected", len(surprise))
    c3.metric("Said yes and showed", len(kept_word))

    left, right = st.columns(2)
    with left:
        st.markdown("**Said yes, never checked in**")
        if no_show:
            st.dataframe(pd.DataFrame({"Member": no_show}), width="stretch", hide_index=True)
        else:
            st.caption("Nobody — everyone who said yes turned up.")
    with right:
        st.markdown("**Checked in, not marked present**")
        if surprise:
            st.dataframe(pd.DataFrame({"Member": surprise}), width="stretch", hide_index=True)
        else:
            st.caption("Nobody unexpected.")

    st.caption(
        "A name on the left may just have forgotten to check in — treat this as a prompt "
        "to ask, not proof of anything."
    )
