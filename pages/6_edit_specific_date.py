import streamlit as st
import pandas as pd
from data_loader import load_data, save_data

st.title("Edit Attendance (Spreadsheet Mode)")
st.caption("Valid status codes: **P** = Present, **A** = Absent, **L** = Late, **O** = Opted Out, **Z** = Excused")
st.warning("⚠️ This editor shows a snapshot from when the page loaded. If the Google Sheet was edited after you opened this page, saving will overwrite those changes. Refresh the page first if unsure.")

# Load CSV
df = load_data()

# Show data editor
edited_df = st.data_editor(
    df,
    num_rows="dynamic",  # allow adding/removing rows
    use_container_width=True,
)

# Save button
if st.button("Save Changes"):
    save_data(edited_df)
    st.success("Attendance saved successfully!")