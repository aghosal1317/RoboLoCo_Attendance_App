import streamlit as st
from slack_integration import get_attendance_by_subteam, SUBTEAM_EMOJIS
from data_loader import load_data, save_data, recalc_percentages
from datetime import date

st.title("Sync from Slack")

# ----------------------------
# Date selector
# ----------------------------
selected_date = st.date_input("Meeting date", value=date.today())
date_str = selected_date.strftime("%m/%d/%y")

# ----------------------------
# Message link input
# ----------------------------
link = st.text_input("Paste Slack message link")

if st.button("Fetch Attendance"):
    if not link:
        st.warning("Please paste a Slack message link.")
    elif "SLACK_TOKEN" not in st.secrets:
        st.error("SLACK_TOKEN not found in secrets. Add it to .streamlit/secrets.toml or Streamlit Cloud settings.")
    else:
        token = st.secrets["SLACK_TOKEN"]
        with st.spinner("Fetching reactions from Slack..."):
            results = get_attendance_by_subteam(token, link)

        if "error" in results:
            st.error(f"Slack API error: {results['error']}")
        else:
            st.session_state["slack_results"] = results
            st.session_state["slack_date_str"] = date_str

# ----------------------------
# Show results if fetched
# ----------------------------
if "slack_results" in st.session_state:
    results = st.session_state["slack_results"]
    saved_date_str = st.session_state["slack_date_str"]

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
    st.caption("Members who reacted with their subteam emoji get P. Everyone else gets A.")

    if st.button("Save to Attendance Sheet", type="primary"):
        fresh_df = load_data()
        fresh_df["Full Name"] = fresh_df["First Name"].str.strip() + " " + fresh_df["Last Name"].str.strip()

        if saved_date_str not in fresh_df.columns:
            fresh_df[saved_date_str] = ""

        # Build set of all present names (lowercased for matching)
        present_names = set()
        for subteam in subteams:
            for name in results.get(subteam, []):
                present_names.add(name.strip().lower())

        unmatched = []
        matched_count = 0

        for idx, row in fresh_df.iterrows():
            full_name = row["Full Name"].strip().lower()
            if full_name in present_names:
                fresh_df.at[idx, saved_date_str] = "P"
                matched_count += 1
            else:
                fresh_df.at[idx, saved_date_str] = "A"

        # Warn about Slack names that didn't match anyone in the roster
        roster_lower = set(fresh_df["Full Name"].str.strip().str.lower())
        for name in present_names:
            if name not in roster_lower:
                unmatched.append(name)

        fresh_df = recalc_percentages(fresh_df)
        save_data(fresh_df)

        st.success(f"✅ Attendance saved for {saved_date_str}! {matched_count} members marked present.")

        if unmatched:
            st.warning(
                f"These Slack names didn't match anyone in the roster — check spelling:\n"
                + "\n".join(f"- {n}" for n in unmatched)
            )

        del st.session_state["slack_results"]
        del st.session_state["slack_date_str"]
