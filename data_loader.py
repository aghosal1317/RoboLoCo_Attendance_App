import re
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

CSV_PATH = "data/attendance.csv"
SHEET_ID = "1bwqw-1DzP1netXcp_L7XLEWg3BZh5glSeshDY9jeprs"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}")
_SUBTEAM_NAMES = {"Executive", "Loco", "Mechanical", "Software", "Coaches"}

# Canonical attendance rules — every page must use these, never its own lists.
# P = Present, L = Late (both count as attended)
# A = Absent, Z = Excused (count in the denominator)
# O = Opted out / optional meeting, blank = no record (ignored entirely)
ATTENDED_CODES = ("P", "L")
COUNTED_CODES = ("P", "L", "A", "Z")


def _get_worksheet():
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=SCOPES
        )
    else:
        creds = Credentials.from_service_account_file(
            "data/service_account.json", scopes=SCOPES
        )
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1


def _deduplicate_columns(columns):
    """
    Google Sheets doesn't auto-rename duplicate column headers the way pandas does.
    This replicates pandas' behavior: second occurrence of 'X' becomes 'X.1', third 'X.2', etc.
    """
    seen = {}
    result = []
    for col in columns:
        if col in seen:
            seen[col] += 1
            result.append(f"{col}.{seen[col]}")
        else:
            seen[col] = 0
            result.append(col)
    return result


def load_data():
    """
    Load attendance from Google Sheet, fall back to local CSV.

    Expected sheet structure (new format):
        Col 0  : Last Name  (or subteam section header)
        Col 1  : First Name
        Col 2  : % Meetings Attended
        Col 3+ : Date columns (MM/DD/YY), with duplicate dates for same-day double sessions

    Section header rows (Executive / Loco / Mechanical / Software / Coaches)
    and count/empty rows are stripped automatically.
    Coaches are excluded from the member roster.
    """
    try:
        ws = _get_worksheet()
        rows = ws.get_all_values()
        if not rows:
            raise ValueError("Empty sheet")
        header = _deduplicate_columns(rows[0])
        df = pd.DataFrame(rows[1:], columns=header)
    except Exception:
        df = pd.read_csv(CSV_PATH)

    df.columns = df.columns.str.strip()

    # Standardise the first two columns regardless of what the sheet calls them
    rename_map = {df.columns[0]: "Last Name", df.columns[1]: "First Name"}
    df.rename(columns=rename_map, inplace=True)

    # ── Subteam extraction ───────────────────────────────────────────────────
    # Two possible formats:
    #   A) Google Sheet: subteam name appears as a standalone row in col 0
    #      (e.g. "Executive", "Loco") — no separate Subteam column.
    #   B) CSV / processed sheet: a "Subteam" column already exists with values.
    # Try format A first; fall back to the existing column if nothing found.
    existing_subteam_col = df["Subteam"].copy() if "Subteam" in df.columns else None

    subteam = None
    subteams = []
    found_headers = False
    for val in df["Last Name"]:
        clean = str(val).strip()
        if clean in _SUBTEAM_NAMES:
            subteam = clean
            found_headers = True
            subteams.append(None)   # mark section header rows for removal
        else:
            subteams.append(subteam)

    if found_headers:
        # Format A — use extracted values
        df["Subteam"] = subteams
    elif existing_subteam_col is not None:
        # Format B — restore the pre-existing column
        df["Subteam"] = existing_subteam_col
    else:
        df["Subteam"] = None

    # ── Row filtering ────────────────────────────────────────────────────────
    # Remove: section header rows, count/blank rows, coach rows
    first_name_col = df["First Name"].astype(str).str.strip()
    df = df[
        first_name_col.ne("") &           # non-empty
        first_name_col.notna() &          # not NaN
        (~first_name_col.str.isnumeric()) # not a count row (e.g. "2", "1")
    ].copy()

    # Exclude coaches from the member roster
    df = df[df["Subteam"] != "Coaches"].copy()

    # ── Full Name ────────────────────────────────────────────────────────────
    df["Full Name"] = (
        df["First Name"].str.strip() + " " + df["Last Name"].str.strip()
    )

    # ── % Meetings Attended ──────────────────────────────────────────────────
    if "% Meetings Attended" in df.columns:
        df["% Meetings Attended"] = (
            df["% Meetings Attended"]
            .astype(str)
            .str.rstrip("%")
            .str.strip()
            .replace({"": "0", "nan": "0"})
            .astype(float)
        )
    else:
        df["% Meetings Attended"] = 0.0

    return df


def get_date_columns(df):
    """
    Return only columns that are actual meeting dates (MM/DD/YY or MM/DD/YY.N format).
    Uses regex so it's robust to schema changes and never accidentally picks up
    metadata columns like Full Name or Subteam.
    """
    return [c for c in df.columns if _DATE_RE.match(str(c))]


def melt_attendance(df):
    """Convert wide attendance table to long format for analysis."""
    date_cols = get_date_columns(df)
    melted = df.melt(
        id_vars=["First Name", "Last Name", "Subteam"],
        value_vars=date_cols,
        var_name="Date",
        value_name="Status",
    )

    # Parse MM/DD/YY (strip any .1 / .2 suffixes for same-day doubles)
    melted["Date"] = (
        melted["Date"]
        .str.replace(r"\.\d+$", "", regex=True)   # drop .1 / .2 suffix
        .pipe(pd.to_datetime, format="%m/%d/%y", errors="coerce")
    )

    melted["Status"] = melted["Status"].astype(str).str.strip()
    melted["Present"] = melted["Status"].isin(ATTENDED_CODES).astype(int)
    melted["Counted"] = melted["Status"].isin(COUNTED_CODES).astype(int)
    return melted


def append_attendance(new_attendance_list):
    """
    Append today's attendance.
    new_attendance_list = ["P", "A", "L", "O", ...] for each member in order.
    """
    df = load_data()
    today_str = datetime.today().strftime("%m/%d/%y")

    if today_str in df.columns:
        print(f"Attendance for {today_str} already exists. Overwriting.")
    df[today_str] = new_attendance_list

    df = recalc_percentages(df)
    save_data(df)


def recalc_percentages(df):
    """Recalculate % Meetings Attended for each member."""
    date_cols = get_date_columns(df)
    for i, row in df.iterrows():
        attended = [row[c] for c in date_cols if str(row[c]).strip() in ATTENDED_CODES]
        counted  = [row[c] for c in date_cols if str(row[c]).strip() in COUNTED_CODES]
        df.at[i, "% Meetings Attended"] = (
            round(len(attended) / len(counted) * 100, 2) if counted else 0.0
        )
    return df


def save_data(df, path=CSV_PATH):
    """Save to local CSV (primary backup) and push to Google Sheet."""
    df = _ordered_columns(df)
    df.to_csv(path, index=False)

    try:
        ws = _get_worksheet()
        data = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
        ws.clear()
        ws.update(data)
    except Exception as e:
        st.warning(f"Saved locally but could not sync to Google Sheet: {e}")


def _ordered_columns(df):
    """
    Return df with columns in a consistent order:
        Last Name | First Name | Full Name | % Meetings Attended | <dates> | Subteam
    Any unexpected extra columns are appended at the end.
    """
    priority = ["Last Name", "First Name", "Full Name", "% Meetings Attended"]
    date_cols = get_date_columns(df)
    tail = ["Subteam"]

    ordered = (
        [c for c in priority if c in df.columns]
        + date_cols
        + [c for c in tail if c in df.columns]
        + [c for c in df.columns if c not in priority + date_cols + tail]
    )
    return df[ordered]
