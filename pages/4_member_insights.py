import streamlit as st
import pandas as pd
import plotly.express as px
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

    # Last attended date
    attended_dates = person_data.loc[person_data["Attended"] == 1, "Date"]
    last_date = attended_dates.max() if not attended_dates.empty else None

    # Consecutive meetings missed (trailing streak of A/Z)
    sorted_statuses = person_data.sort_values("Date")["Status"].tolist()
    consecutive_missed = 0
    for s in reversed(sorted_statuses):
        if s in ["A", "Z"]:
            consecutive_missed += 1
        else:
            break

    m1, m2, m3 = st.columns(3)
    m1.metric("% Meetings Attended", f"{attendance_percent:.2f}%")
    m2.metric("Last Attended", str(last_date.date()) if last_date is not None else "N/A")
    m3.metric("Consecutive Missed", consecutive_missed)

    # Trend chart: cumulative % over time
    chart_data = person_data.dropna(subset=["Date"]).sort_values("Date").copy()
    cum_attended = chart_data["Attended"].cumsum()
    cum_counted = chart_data["Counted"].cumsum()
    chart_data = chart_data[cum_counted > 0].copy()
    cum_attended = chart_data["Attended"].cumsum()
    cum_counted = chart_data["Counted"].cumsum()
    chart_data["Cumulative %"] = cum_attended / cum_counted * 100

    fig = px.line(
        chart_data,
        x="Date",
        y="Cumulative %",
        markers=True,
        title="Cumulative Attendance Over Time"
    )
    fig.update_layout(yaxis_range=[0, 100], xaxis_title="Date", yaxis_title="Attendance (%)")
    st.plotly_chart(fig, use_container_width=True)