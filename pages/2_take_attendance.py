import streamlit as st
from data_loader import load_data, save_data, recalc_percentages
from datetime import date

# ----------------------------
# Load data
# ----------------------------
df = load_data()

# Ensure Full Name exists
df["Full Name"] = df["First Name"].str.strip() + " " + df["Last Name"].str.strip()

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

st.divider()

# ----------------------------
# Search box
# ----------------------------
search_name = st.text_input("Search for a member (leave blank to show all)")

# Filter members by search term (case-insensitive)
if search_name:
    filtered_df = df[df["Full Name"].str.contains(search_name, case=False, na=False)]
else:
    filtered_df = df.copy()

# ----------------------------
# Create checkboxes for filtered members (3-column grid)
# ----------------------------
names = list(filtered_df["Full Name"])
cols = st.columns(3)
attendance = {name: cols[i % 3].checkbox(name) for i, name in enumerate(names)}

# ----------------------------
# Submit button
# ----------------------------
if st.button("Submit Attendance"):
    # Re-pull latest from Sheet before writing to avoid overwriting direct edits
    fresh_df = load_data()
    fresh_df["Full Name"] = fresh_df["First Name"].str.strip() + " " + fresh_df["Last Name"].str.strip()

    if date_str not in fresh_df.columns:
        fresh_df[date_str] = ""

    absent_code = "O" if is_optional else "A"

    for name, present in attendance.items():
        match = fresh_df["Full Name"] == name
        if match.any():
            fresh_df.loc[match, date_str] = "P" if present else absent_code
        else:
            st.warning(f"No row found for {name} – check CSV for spelling or extra spaces.")

    fresh_df = recalc_percentages(fresh_df)
    save_data(fresh_df)
    st.success(f"✅ Attendance saved for {date_str}!")
