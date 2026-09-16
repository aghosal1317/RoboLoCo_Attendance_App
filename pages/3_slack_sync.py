import streamlit as st
from slack_integration import get_attendance_by_subteam, SUBTEAM_EMOJIS
from data_loader import load_data, save_data, recalc_percentages, write_attendance, is_saturday
from settings import get_secret
from datetime import date

st.title("Sync from Slack")

# ----------------------------
# Date selector + optional meeting toggle
# ----------------------------
opt_col, date_col = st.columns([1, 2])

with opt_col:
    is_optional = st.toggle("Optional Meeting", value=False,
                            help="Absent members get O (no % deduction) instead of A.")
with date_col:
    selected_date = st.date_input("Meeting date", value=date.today())

date_str = selected_date.strftime("%m/%d/%y")

if is_optional:
    st.caption(f"Optional meeting — non-reactors will be marked **O** for {date_str}")
else:
    st.caption(f"Regular meeting — non-reactors will be marked **A** for {date_str}")

if is_saturday(date_str):
    st.caption(f"🗓️ {date_str} is a **Saturday** (double session) — attendance will be recorded in two columns and count twice.")

# ----------------------------
# Message link input
# ----------------------------
link = st.text_input("Paste Slack message link")

if st.button("Fetch Attendance"):
    token = get_secret("SLACK_TOKEN")
    if not link:
        st.warning("Please paste a Slack message link.")
    elif not token:
        st.error("SLACK_TOKEN not found in secrets. Add it to .streamlit/secrets.toml or Streamlit Cloud settings.")
    else:
        with st.spinner("Fetching reactions from Slack..."):
            results = get_attendance_by_subteam(token, link)

        if "error" in results:
            st.error(f"Slack API error: {results['error']}")
        else:
            st.session_state["slack_results"] = results
            st.session_state["slack_date_str"] = date_str
            st.session_state["slack_is_optional"] = is_optional

# ----------------------------
# Show results if fetched
# ----------------------------
if "slack_results" in st.session_state:
    results = st.session_state["slack_results"]
    saved_date_str = st.session_state["slack_date_str"]
    saved_is_optional = st.session_state["slack_is_optional"]

    st.divider()
    st.subheader(f"Reactions for {saved_date_str}")

    # Per-subteam breakdown
    subteams = list(SUBTEAM_EMOJIS.values())
    cols = st.columns(len(subteams))
    for col, subteam in zip(cols, subteams):
        members = results.get(subteam, [])
        col.metric(subteam, len(members))
        for name in sorted(members):
            col.write(f"✅ {name}")

    # Won't attend
    wont = results.get("wont_attend", [])
    with st.expander(f"Won't Attend ({len(wont)})"):
        if wont:
            for name in sorted(wont):
                st.write(f"❌ {name}")
        else:
            st.caption("No one marked won't attend.")

    total_present = sum(len(results.get(s, [])) for s in subteams)
    st.info(f"**{total_present}** members reacted as attending across all subteams.")

    st.divider()

    # ----------------------------
    # Match against roster + submit
    # ----------------------------
    st.subheader("Submit Attendance")
    absent_label = "O (optional, no deduction)" if saved_is_optional else "A"
    st.caption(f"Members who reacted with their subteam emoji get P. Everyone else gets **{absent_label}**.")

    if st.button("Save to Attendance Sheet", type="primary"):
        fresh_df = load_data()
        present_names = [name for s in subteams for name in results.get(s, [])]
        absent_code = "O" if saved_is_optional else "A"

        matched_count, unmatched = write_attendance(fresh_df, saved_date_str, present_names, absent_code)
        fresh_df = recalc_percentages(fresh_df)
        saved = save_data(fresh_df)

        if saved:
            st.success(f"✅ Attendance saved for {saved_date_str}! {matched_count} members marked present.")

        if unmatched:
            st.warning(
                "These Slack names didn't match anyone in the roster — check spelling:\n"
                + "\n".join(f"- {n}" for n in unmatched)
            )

        if saved:
            del st.session_state["slack_results"]
            del st.session_state["slack_date_str"]
            del st.session_state["slack_is_optional"]
