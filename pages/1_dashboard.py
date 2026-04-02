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
# Calculate % Meetings Attended dynamically
# ----------------------------
date_cols = [c for c in df.columns if c not in ["First Name", "Last Name", "Subteam"]]
df["% Meetings Attended"] = df[date_cols].apply(
    lambda row: round(
        sum(1 for x in row if x in ["P", "L"]) / max(sum(1 for x in row if x in ["P", "L", "A", "O"]), 1) * 100, 2
    ), axis=1
)

# ----------------------------
# Metrics row
# ----------------------------
today = date.today().strftime("%m/%d/%y")
today_data = melted[melted["Date"].dt.strftime("%m/%d/%y") == today]
today_pct = round(today_data["Present"].mean() * 100, 1) if len(today_data) else None

overall_avg = round(df["% Meetings Attended"].mean(), 1)
low_count = len(df[df["% Meetings Attended"] < 70])

col1, col2, col3 = st.columns(3)
col1.metric("Today's Attendance", f"{today_pct}%" if today_pct else "No data yet")
col2.metric("Overall Average", f"{overall_avg}%")
col3.metric("Members Below 70%", low_count)

# ----------------------------
# Alerts
# ----------------------------
if low_count > 0:
    st.warning(f"⚠️ {low_count} members are below 70% attendance")

weekly = melted[melted["Date"] >= pd.Timestamp(date.today() - timedelta(days=7))]
prev_week = melted[(melted["Date"] >= pd.Timestamp(date.today() - timedelta(days=14))) &
                   (melted["Date"] < pd.Timestamp(date.today() - timedelta(days=7)))]

if len(weekly) and len(prev_week):
    if weekly["Present"].mean() < prev_week["Present"].mean():
        st.error("📉 Attendance dropped compared to last week")

# ----------------------------
# Weekly trend line chart
# ----------------------------
st.subheader("Weekly trend")
weekly_trend = (
    melted.groupby(melted["Date"].dt.to_period("W").dt.start_time)["Present"]
    .mean() * 100
).reset_index()
weekly_trend.columns = ["Week", "% Meetings Attended"]

fig = px.line(weekly_trend, x="Week", y="% Meetings Attended", markers=True)
fig.update_layout(yaxis_range=[50, 100])
st.plotly_chart(fig, use_container_width=True)

# ----------------------------
# Action Center
# ----------------------------
st.subheader("Action Center")
low_members = df[df["% Meetings Attended"] < 70]

if len(low_members) > 0:
    for _, row in low_members.iterrows():
        st.write(f"⚠️ {row['First Name']} {row['Last Name']} below 70%")