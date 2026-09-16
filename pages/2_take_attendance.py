import streamlit as st
from data_loader import load_data, save_data, recalc_percentages, write_attendance, is_saturday
from datetime import date

# ----------------------------
# Load data
# ----------------------------
df = load_data()

st.title("Take Attendance")
st.info("Once the Slack Bot is live, this page may no longer be needed.")

# ----------------------------
# Date selector + optional meeting toggle
# ----------------------------
opt_col, date_col = st.columns([1, 2])

with opt_col:
    is_optional = st.toggle("Optional Meeting", value=False,
                            help="Present members get P (counts positively). Absent members get O (no deduction).")

with date_col:
    selected_date = st.date_input("Meeting date", value=date.today())

date_str = selected_date.strftime("%m/%d/%y")

if is_optional:
    st.caption(f"Optional meeting — absences will be marked **O** (no % deduction) for {date_str}")
else:
    st.caption(f"Regular meeting — absences will be marked **A** for {date_str}")

if is_saturday(date_str):
    st.caption(f"🗓️ {date_str} is a **Saturday** (double session) — attendance will be recorded in two columns and count twice.")

st.divider()

# ----------------------------
# Selections live in session state so they survive searching / filtering.
# (A checkbox that scrolls out of the filtered grid is unmounted and would
#  otherwise forget its value.)
# ----------------------------
if "manual_checked" not in st.session_state:
    st.session_state.manual_checked = set()


def _toggle(name):
    if st.session_state[f"att_{name}"]:
        st.session_state.manual_checked.add(name)
    else:
        st.session_state.manual_checked.discard(name)


all_names = df["Full Name"].tolist()

# ----------------------------
# Search box
# ----------------------------
search_name = st.text_input("Search for a member (leave blank to show all)")

if search_name:
    filtered_df = df[df["Full Name"].str.contains(search_name, case=False, na=False)]
else:
    filtered_df = df

# ----------------------------
# Checkbox grid for filtered members
# ----------------------------
names = list(filtered_df["Full Name"])
cols = st.columns(3)
for i, name in enumerate(names):
    cols[i % 3].checkbox(
        name,
        value=name in st.session_state.manual_checked,
        key=f"att_{name}",
        on_change=_toggle,
        args=(name,),
    )

selected = sorted(n for n in st.session_state.manual_checked if n in all_names)
st.caption(f"**{len(selected)}** of {len(all_names)} members marked present"
           + (f": {', '.join(selected)}" if selected else ""))

if selected and st.button("Clear selections"):
    st.session_state.manual_checked = set()
    st.rerun()

# ----------------------------
# Submit button
# ----------------------------
if st.button("Submit Attendance", type="primary"):
    # Re-pull latest from Sheet before writing to avoid overwriting direct edits
    fresh_df = load_data()
    absent_code = "O" if is_optional else "A"
    matched, unrecognized = write_attendance(fresh_df, date_str, selected, absent_code)
    fresh_df = recalc_percentages(fresh_df)
    if save_data(fresh_df):
        st.success(f"✅ Attendance saved for {date_str}! {matched} present, "
                   f"{len(fresh_df) - matched} marked {absent_code}.")
        st.session_state.manual_checked = set()
    if unrecognized:
        st.warning("These names weren't found in the roster (was it edited since you opened this page?): "
                   + ", ".join(unrecognized))
