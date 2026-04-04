import streamlit as st
from data_loader import load_data, save_data, recalc_percentages
from datetime import datetime

# ----------------------------
# Load data
# ----------------------------
df = load_data()

# Ensure Full Name exists
df["Full Name"] = df["First Name"].str.strip() + " " + df["Last Name"].str.strip()

st.title("Take Attendance")
st.text("This page will likely not be needed when Slack Bot is implemented")

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
# Create checkboxes for filtered members
# ----------------------------
attendance = {name: st.checkbox(name) for name in filtered_df["Full Name"]}

# ----------------------------
# Submit button
# ----------------------------
if st.button("Submit Attendance"):
    today_col = datetime.today().strftime("%m/%d/%y")
    
    # Create new column if it doesn't exist
    if today_col not in df.columns:
        df[today_col] = ""  

    # Update attendance directly by Full Name
    for name, present in attendance.items():
        match = df["Full Name"] == name
        if match.any():
            df.loc[match, today_col] = "P" if present else "A"
        else:
            st.warning(f"No row found for {name} – check CSV for spelling or extra spaces.")
    
    # Recalculate attendance percentages
    df = recalc_percentages(df)
    
    # Save updated CSV
    save_data(df)
    
    st.success(f"✅ Attendance saved for {today_col}!")