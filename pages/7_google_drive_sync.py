import streamlit as st
import gspread
from data_loader import load_data, recalc_percentages, get_date_columns, _get_credentials, _ordered_columns
from settings import get_sheet_id, sheet_url, parse_sheet_id

st.title("Sync CSV to Google Sheet")
st.caption(
    "Pushes the full attendance dataset to a Google Sheet. Defaults to the sheet "
    "configured on the Settings page; paste a different URL to export elsewhere."
)

# Load current data (from the configured sheet, or the local CSV backup)
df = load_data()

target = st.text_input(
    "Google Sheet URL or ID (must be shared with the service account as Editor)",
    sheet_url(get_sheet_id()),
)

if st.button("Sync Now", type="primary"):
    sheet_id = parse_sheet_id(target)
    if not sheet_id:
        st.error("Enter a valid Google Sheet URL or spreadsheet ID.")
    else:
        try:
            client = gspread.authorize(_get_credentials())
            worksheet = client.open_by_key(sheet_id).sheet1

            df_to_upload = df.copy()

            # Fill blank attendance cells with O so past dates don't show as gaps
            for c in get_date_columns(df_to_upload):
                df_to_upload[c] = df_to_upload[c].fillna("").replace("", "O")

            # Recalculate % Meetings Attended (canonical rule from data_loader)
            df_to_upload = _ordered_columns(recalc_percentages(df_to_upload))

            # Clear existing sheet and upload
            worksheet.clear()
            worksheet.update(
                [df_to_upload.columns.tolist()]
                + df_to_upload.fillna("").astype(str).values.tolist()
            )

            st.success(f"✅ Synced {len(df_to_upload)} members to **{worksheet.spreadsheet.title}**.")

        except Exception as e:
            st.error(f"Unexpected error: {e}")
