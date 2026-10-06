import streamlit as st
from slack_integration import (
    get_attendance_by_subteam, SUBTEAM_EMOJIS, SUBTEAM_ALIASES, NON_ROSTER_SUBTEAMS,
)
from data_loader import load_data, save_data, recalc_percentages, write_attendance, is_saturday
from settings import get_secret
from datetime import date

ALL_SUBTEAMS = sorted(set(SUBTEAM_EMOJIS.values()))
# Subteams whose attendance is actually recorded (coaches aren't roster members)
ROSTER_SUBTEAMS = [s for s in ALL_SUBTEAMS if s not in NON_ROSTER_SUBTEAMS]


def label(subteam):
    return SUBTEAM_ALIASES.get(subteam, subteam)


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

# ----------------------------
# Show results if fetched
# ----------------------------
if "slack_results" in st.session_state:
    results = st.session_state["slack_results"]

    st.divider()
    st.subheader("Reactions on this message")

    if results.get("text"):
        with st.expander("Message text"):
            st.write(results["text"])

    # Per-subteam breakdown
    cols = st.columns(len(ROSTER_SUBTEAMS))
    for col, subteam in zip(cols, ROSTER_SUBTEAMS):
        members = results.get(subteam, [])
        col.metric(label(subteam), len(members))
        for name in sorted(members):
            col.write(f"✅ {name}")

    # Groups that react but aren't tracked on the roster (coaches)
    for subteam in NON_ROSTER_SUBTEAMS:
        reacted = results.get(subteam, [])
        if reacted:
            with st.expander(f"{subteam} who reacted ({len(reacted)}) — not recorded"):
                st.caption(
                    f"{subteam} aren't attendance-tracked members, so nothing is written "
                    "for them. Listed here so you can see who responded."
                )
                for name in sorted(reacted):
                    st.write(f"• {name}")

    # Won't attend
    wont = results.get("wont_attend", [])
    with st.expander(f"Won't Attend ({len(wont)})"):
        if wont:
            for name in sorted(wont):
                st.write(f"❌ {name}")
        else:
            st.caption("No one marked won't attend.")

    total_present = sum(len(results.get(s, [])) for s in ALL_SUBTEAMS)
    st.info(f"**{total_present}** members reacted as attending across all subteams.")

    st.divider()

    # ----------------------------
    # Which subteams this meeting was for
    # ----------------------------
    st.subheader("Who was this meeting for?")
    detected_all = set(results.get("invited") or ALL_SUBTEAMS)
    detected = sorted(s for s in detected_all if s in ROSTER_SUBTEAMS)
    uninvited_detected = [s for s in ROSTER_SUBTEAMS if s not in detected]

    if uninvited_detected:
        st.info(
            "This message only asked **" + "**, **".join(label(s) for s in detected) + "** to react — "
            "no emoji for " + ", ".join(f"**{label(s)}**" for s in uninvited_detected) + ". "
            "Members of the subteams you leave unticked below won't be marked absent."
        )
    else:
        st.caption("This message asked every subteam to react.")

    invited = st.multiselect(
        "Subteams this meeting applied to",
        options=ROSTER_SUBTEAMS,
        default=detected,
        format_func=label,
        help="Members of any subteam left out of this list are not marked absent for this meeting.",
    )

    uninvited = [s for s in ROSTER_SUBTEAMS if s not in invited]
    uninvited_code = "O"
    if uninvited:
        uninvited_code = st.radio(
            f"What should members of {', '.join(label(s) for s in uninvited)} get?",
            options=["O", "A"],
            format_func=lambda c: {
                "O": "O — opted out (no effect on their percentage)",
                "A": "A — absent (counts against their percentage)",
            }[c],
            horizontal=False,
        )

    # ----------------------------
    # Match against roster + submit
    # ----------------------------
    st.subheader("Submit Attendance")
    absent_label = "O (optional, no deduction)" if is_optional else "A"
    st.caption(
        f"Saving to **{date_str}**. Members of "
        f"{', '.join(label(s) for s in invited) or '(no subteams selected)'} "
        f"who reacted with their subteam emoji get **P**; the rest of those subteams get **{absent_label}**."
        + (f" Everyone in {', '.join(label(s) for s in uninvited)} gets **{uninvited_code}**." if uninvited else "")
    )

    if not invited:
        st.warning("Select at least one subteam before saving.")

    if st.button("Save to Attendance Sheet", type="primary", disabled=not invited):
        fresh_df = load_data()
        present_names = [name for s in ROSTER_SUBTEAMS for name in results.get(s, [])]
        absent_code = "O" if is_optional else "A"

        matched_count, unmatched = write_attendance(
            fresh_df, date_str, present_names, absent_code,
            only_subteams=invited, uninvited_code=uninvited_code,
        )
        fresh_df = recalc_percentages(fresh_df)
        saved = save_data(fresh_df)

        if saved:
            st.success(f"✅ Attendance saved for {date_str}! {matched_count} members marked present.")
            if uninvited:
                skipped = int(fresh_df["Subteam"].isin(uninvited).sum())
                st.caption(f"{skipped} members in {', '.join(label(s) for s in uninvited)} were marked {uninvited_code}.")

        if unmatched:
            st.warning(
                "These Slack names didn't match anyone in the roster — check spelling, "
                "or add them to the sheet if they're new:\n"
                + "\n".join(f"- {n}" for n in unmatched)
            )

        if saved:
            del st.session_state["slack_results"]
