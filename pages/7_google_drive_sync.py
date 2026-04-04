import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from data_loader import load_data, save_data
from datetime import datetime

st.title("Sync CSV to Google Sheet")

# Load CSV
df = load_data()

sheet_url = st.text_input(
    "Enter Google Sheet URL (must be shared with your service account)",
    "https://docs.google.com/spreadsheets/d/1C9qau6QvJL2o-TcvZupEroCn-F8H7tT0Q7Zbvn1m64Q/edit?usp=sharing"
)

if st.button("Sync Now"):
    if not sheet_url or "https://docs.google.com/spreadsheets/d/" not in sheet_url:
        st.error("Enter a valid Google Sheet URL.")
    else:
        try:
            # Connect to Google Sheet
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], #"data/service_account.json" for local testing by Aneesh
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
            client = gspread.authorize(creds)

            sheet_id = sheet_url.split("/d/")[1].split("/")[0]
            sheet = client.open_by_key(sheet_id)
            worksheet = sheet.sheet1

            # Copy the dataframe
            df_to_upload = df.copy()

            # Identify attendance columns
            date_cols = [c for c in df_to_upload.columns if c not in ["First Name", "Last Name", "Subteam", "% Meetings Attended"]]

            # Fill missing values only for past dates
            for c in date_cols:
                df_to_upload[c] = df_to_upload[c].fillna("O").replace("", "O")

            # Recalculate % Meetings Attended dynamically
            for i, row in df_to_upload.iterrows():
                statuses = [row[c] for c in date_cols if row[c] in ["P", "A", "L"]]
                if statuses:
                    df_to_upload.at[i, "% Meetings Attended"] = round(statuses.count("P") / len(statuses) * 100, 2)
                else:
                    df_to_upload.at[i, "% Meetings Attended"] = 0

            # Clear existing sheet and upload
            worksheet.clear()
            worksheet.update([df_to_upload.columns.values.tolist()] + df_to_upload.values.tolist())

            st.success("✅ CSV successfully synced to Google Sheet!")

        except Exception as e:
            st.error(f"Unexpected error: {e}")