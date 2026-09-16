import streamlit as st
import pandas as pd
from data_loader import load_data, save_data, recalc_percentages

st.title("Edit Attendance (Spreadsheet Mode)")
st.caption("Valid status codes: **P** = Present, **A** = Absent, **L** = Late, **O** = Opted Out, **Z** = Excused")
st.warning("⚠️ This editor shows a snapshot from when the page loaded. If the Google Sheet was edited after you opened this page, saving will overwrite those changes. Refresh the page first if unsure.")

# Load from the sheet (or the local backup if the sheet is unreachable)
df = load_data()
from_backup = df.attrs.get("source") == "csv"

# Show data editor
edited_df = st.data_editor(
    df,
    num_rows="dynamic",  # allow adding/removing rows
    use_container_width=True,
)

# Save button — disabled when the data didn't come from the live sheet, so a
# stale backup can never be pushed over it.
if st.button("Save Changes", disabled=from_backup,
             help="Disabled: the sheet couldn't be loaded, so saving would overwrite it with the backup." if from_backup else None):
    edited_df = recalc_percentages(edited_df)
    edited_df.attrs["source"] = df.attrs.get("source")
    if save_data(edited_df):
        st.success("Attendance saved successfully!")
