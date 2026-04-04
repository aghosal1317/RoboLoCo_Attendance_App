import streamlit as st
import pandas as pd
import plotly.express as px
from data_loader import load_data, melt_attendance
from datetime import date, timedelta

# ----------------------------
# Load data
# ----------------------------
df = load_data()
melted = melt_attendance(df)

st.title("Dashboard")

# ----------------------------
# Calculate % Meetings Attended
# ----------------------------
date_cols = [c for c in df.columns if c not in ["First Name", "Last Name", "Subteam"]]

df["% Meetings Attended"] = df[date_cols].apply(
    lambda row: round(
        sum(1 for x in row if x in ["P", "L"]) /
        max(sum(1 for x in row if x in ["P", "L", "A", "O"]), 1) * 100,
        2
    ),
    axis=1
)

# ----------------------------
# Date range info
# ----------------------------
start_date = melted["Date"].min()
end_date = melted["Date"].max()

# ----------------------------
# Latest meeting attendance (most recent date in data)
# ----------------------------
latest_meeting_date = melted["Date"].max()
latest_data = melted[melted["Date"] == latest_meeting_date]
latest_pct = round(latest_data["Present"].mean() * 100, 1) if len(latest_data) else None
latest_date_str = latest_meeting_date.strftime("%m/%d/%y")

# ----------------------------
# Overall stats
# ----------------------------
overall_avg = round(df["% Meetings Attended"].mean(), 1)
low_members = df[df["% Meetings Attended"] < 70]
low_count = len(low_members)

# ----------------------------
# Metrics row
# ----------------------------
col1, col2, col3 = st.columns(3)

col1.metric(
    f"Attendance on {latest_date_str}",
    f"{latest_pct}%" if latest_pct is not None else "No data"
)

col2.metric(
    "Overall Average",
    f"{overall_avg}%",
    help=f"From {start_date.strftime('%m/%d/%y')} to {end_date.strftime('%m/%d/%y')}"
)

col3.metric("Members Below 70%", low_count)

# ----------------------------
# Alerts
# ----------------------------
if low_count > 0:
    st.warning(f"⚠️ {low_count} members are below 70% attendance")

weekly = melted[melted["Date"] >= pd.Timestamp(date.today() - timedelta(days=7))]
prev_week = melted[
    (melted["Date"] >= pd.Timestamp(date.today() - timedelta(days=14))) &
    (melted["Date"] < pd.Timestamp(date.today() - timedelta(days=7)))
]

if len(weekly) and len(prev_week):
    if weekly["Present"].mean() < prev_week["Present"].mean():
        st.error("📉 Attendance dropped compared to last week")

# ----------------------------
# Weekly trend chart
# ----------------------------
st.subheader("Weekly Trend")

weekly_trend = (
    melted.groupby(melted["Date"].dt.to_period("W").dt.start_time)["Present"]
    .mean() * 100
).reset_index()

weekly_trend.columns = ["Week", "% Meetings Attended"]

fig = px.line(weekly_trend, x="Week", y="% Meetings Attended", markers=True)
fig.update_layout(yaxis_range=[50, 100])

st.plotly_chart(fig, use_container_width=True)

# ----------------------------
# Action Center (BOTTOM)
# ----------------------------
st.subheader("Action Center")

show_low = st.button(f"Show Members Below 70% ({low_count})")

if show_low and low_count > 0:
    display_df = low_members[
        ["First Name", "Last Name", "Subteam", "% Meetings Attended"]
    ].sort_values("% Meetings Attended")

    st.dataframe(
        display_df.style.background_gradient(
            subset=["% Meetings Attended"], cmap="Reds"
        ),
        use_container_width=True
    )