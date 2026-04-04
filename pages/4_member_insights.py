import streamlit as st
import pandas as pd
from data_loader import load_data, melt_attendance

# ----------------------------
# Load data
# ----------------------------
df = load_data()
melted = melt_attendance(df)

st.title("Member Insights")

# Create full name column
df["Full Name"] = df["First Name"].str.strip() + " " + df["Last Name"].str.strip()

# ----------------------------
# Search feature
# ----------------------------
search_name = st.text_input("Search for a member (leave blank to show all)")

# Filter members based on search (case-insensitive)
if search_name:
    filtered_df = df[df["Full Name"].str.contains(search_name, case=False, na=False)]
else:
    filtered_df = df.copy()

if filtered_df.empty:
    st.warning("No members match your search.")
else:
    # Select member from filtered list
    selected = st.selectbox("Select Member", filtered_df["Full Name"])
    person = df[df["Full Name"] == selected].iloc[0]

    # ----------------------------
    # Filter melted data for this person
    # ----------------------------
    person_data = melted[
        (melted["First Name"] == person["First Name"]) &
        (melted["Last Name"] == person["Last Name"])
    ].copy()

    # ----------------------------
    # Compute dynamic attendance
    # P/L counts as attended, A/Z counts in denominator, O ignored
    # ----------------------------
    person_data["Attended"] = person_data["Status"].isin(["P", "L"]).astype(int)
    person_data["Counted"] = person_data["Status"].isin(["P", "L", "A", "Z"]).astype(int)

    # Overall % Meetings Attended
    total_attended = person_data["Attended"].sum()
    total_counted = person_data["Counted"].sum()
    attendance_percent = (total_attended / total_counted * 100) if total_counted > 0 else 0

    st.metric("% Meetings Attended", f"{attendance_percent:.2f}%")

    # Last attended date
    attended_dates = person_data.loc[person_data["Attended"] == 1, "Date"]
    last_date = attended_dates.max() if not attended_dates.empty else None
    st.metric("Last Attended", str(last_date.date()) if last_date is not None else "N/A")

    # Trend chart: cumulative % over time
    person_data["Cumulative %"] = (
        person_data["Attended"].cumsum() / person_data["Counted"].cumsum() * 100
    )

    st.line_chart(person_data.set_index("Date")["Cumulative %"])