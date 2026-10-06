import streamlit as st
from slack_integration import (
    get_attendance_by_subteam, SUBTEAM_EMOJIS, SUBTEAM_ALIASES, find_meeting_date,
)
from data_loader import (
    load_data, save_data, recalc_percentages, write_attendance, is_saturday,
    existing_attendance, unmatched_subteams,
)
from settings import get_secret
from datetime import date

ALL_SUBTEAMS = sorted(set(SUBTEAM_EMOJIS.values()))


def label(subteam):
    return SUBTEAM_ALIASES.get(subteam, subteam)


st.title("Sync from Slack")

# The "use the message's date" button can't assign to the date widget's own key
# after the widget exists, so it stashes the date here and reruns; we apply it
# before the widget is built.
if "_pending_meeting_date" in st.session_state:
    st.session_state["slack_meeting_date"] = st.session_state.pop("_pending_meeting_date")

# ----------------------------
# Date selector + optional meeting toggle
# ----------------------------
opt_col, date_col = st.columns([1, 2])

with opt_col:
    is_optional = st.toggle("Optional Meeting", value=False,
                            help="Absent members get O (no % deduction) instead of A.")
with date_col:
    selected_date = st.date_input("Meeting date", value=date.today(), key="slack_meeting_date")

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
@st.cache_data(ttl=60, show_spinner=False)
def _roster_snapshot():
    """Roster for the pre-save checks. Cached briefly so reruns don't re-hit Sheets."""
    return load_data()


if "slack_results" in st.session_state:
    results = st.session_state["slack_results"]
    roster_df = _roster_snapshot()

    st.divider()
    st.subheader("Reactions on this message")

    if results.get("text"):
        with st.expander("Message text"):
            st.write(results["text"])

    # Per-subteam breakdown
    cols = st.columns(len(ALL_SUBTEAMS))
    for col, subteam in zip(cols, ALL_SUBTEAMS):
        members = results.get(subteam, [])
        col.metric(label(subteam), len(members))
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

    total_present = sum(len(results.get(s, [])) for s in ALL_SUBTEAMS)
    st.info(f"**{total_present}** people reacted as attending across all groups.")

    st.divider()

    # ----------------------------
    # Which subteams this meeting was for
    # ----------------------------
    st.subheader("Who was this meeting for?")
    raw_invited = set(results.get("invited") or ())
    could_not_tell = not raw_invited
    detected = sorted(raw_invited) if raw_invited else list(ALL_SUBTEAMS)
    uninvited_detected = [s for s in ALL_SUBTEAMS if s not in detected]

    if could_not_tell:
        st.warning(
            "Couldn't find any subteam emoji in this message, so **the whole team is assumed "
            "invited** — everyone who didn't react will be marked absent as usual. "
            "Untick any subteam the meeting wasn't for."
        )
    elif uninvited_detected:
        st.info(
            "This message only asked **" + "**, **".join(label(s) for s in detected) + "** to react — "
            "no emoji for " + ", ".join(f"**{label(s)}**" for s in uninvited_detected) + ". "
            "Members of the subteams you leave unticked below won't be marked absent."
        )
    else:
        st.caption("This message asked every subteam to react.")

    invited = st.multiselect(
        "Subteams this meeting applied to",
        options=ALL_SUBTEAMS,
        default=detected,
        format_func=label,
        help="Members of any subteam left out of this list are not marked absent for this meeting.",
    )

    uninvited = [s for s in ALL_SUBTEAMS if s not in invited]
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
    # Double-check: does the message agree with what the app is about to do?
    # ----------------------------
    st.divider()
    st.subheader("Double-check before saving")

    absent_code = "O" if is_optional else "A"
    problems = 0
    date_conflict = False

    # 1. The date named in the message vs. the date picker
    msg_date = find_meeting_date(results.get("text", ""), today=date.today())
    if msg_date is None:
        st.caption("• No date found in the message — check the date picker above yourself.")
    elif msg_date == selected_date:
        st.success(f"• Date matches: the message says **{msg_date.strftime('%m/%d/%y')}**, "
                   f"and that's what will be written.")
    else:
        problems += 1
        date_conflict = True
        st.error(
            f"• **Date mismatch.** The message is about "
            f"**{msg_date.strftime('%m/%d/%y')}**, but attendance would be written to "
            f"**{selected_date.strftime('%m/%d/%y')}**."
        )
        if st.button(f"Use the message's date ({msg_date.strftime('%m/%d/%y')})"):
            st.session_state["_pending_meeting_date"] = msg_date
            st.rerun()

    # 2. Is something already recorded for this date?
    already = existing_attendance(roster_df, date_str)
    if already:
        problems += 1
        breakdown = ", ".join(f"{n}×{c}" for c, n in sorted(already["codes"].items()))
        st.warning(
            f"• **{date_str} already has {already['members']} entries** ({breakdown}). "
            "Saving replaces every one of them."
        )

    # 3. Reacting names that aren't on the roster — shown before the write, not after
    roster_lower = set(roster_df["Full Name"].str.strip().str.lower())
    reacted = {n.strip().lower(): n for s_ in ALL_SUBTEAMS for n in results.get(s_, [])}
    strangers = sorted(orig for low, orig in reacted.items() if low not in roster_lower)
    if strangers:
        problems += 1
        st.warning(
            f"• **{len(strangers)} {'person' if len(strangers) == 1 else 'people'} reacted "
            "who aren't on the roster** — they won't be recorded. Add them to the sheet, "
            "or check the spelling of their Slack display name:\n"
            + "\n".join(f"    - {n}" for n in strangers)
        )

    # 4. Do the app's subteam names exist in the sheet at all?
    # A subteam with no members is normal (most sheets have no Mentors), so only
    # the total mismatch is worth flagging — that's the case where the invite
    # list is meaningless and the whole-team fallback kicks in.
    missing = unmatched_subteams(roster_df, invited)
    if invited and len(missing) == len(invited):
        problems += 1
        st.warning(
            "• **None of the selected subteams match anyone in the sheet.** The `Subteam` "
            f"column uses different names ({', '.join(sorted(set(roster_df['Subteam'].dropna()))[:4])}…), "
            f"so the invite list is being ignored and everyone absent will be marked **{absent_code}**. "
            "That's the safe outcome, but fix the sheet's subteam names to use the invite list."
        )

    # 5. Anyone who will be recorded "didn't apply" instead of absent
    if uninvited and uninvited_code != absent_code:
        skipped = int(roster_df["Subteam"].isin(uninvited).sum())
        if skipped:
            problems += 1
            st.warning(
                f"• **{skipped} members** in {', '.join(label(s_) for s_ in uninvited)} "
                f"will be recorded **{uninvited_code}** (doesn't count), not **{absent_code}**, "
                "because the message didn't ask their subteam to react. "
                "If they were meant to be at this meeting, tick their subteam above."
            )

    if not problems:
        st.caption("Everything lines up.")

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

    override = True
    if date_conflict:
        override = st.checkbox(
            f"I know the dates differ — save to {date_str} anyway",
            help="The message names a different date. Tick this only if the picker is the one you want.",
        )

    if st.button("Save to Attendance Sheet", type="primary",
                 disabled=not invited or not override):
        fresh_df = load_data()
        present_names = [name for s in ALL_SUBTEAMS for name in results.get(s, [])]

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
            _roster_snapshot.clear()   # the sheet just changed
            del st.session_state["slack_results"]
