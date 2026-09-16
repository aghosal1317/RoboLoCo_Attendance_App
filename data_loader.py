import re
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

from settings import get_sheet_id, get_secret

CSV_PATH = "data/attendance.csv"
SERVICE_ACCOUNT_PATH = "data/service_account.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_DATE_RE = re.compile(r"^(\d{2}/\d{2}/\d{2})(?:\.(\d+))?$")
_SUBTEAM_NAMES = {"Executive", "Loco", "Mechanical", "Software", "Coaches"}

# Canonical attendance rules — every page must use these, never its own lists.
# P = Present, L = Late (both count as attended)
# A = Absent, Z = Excused (count in the denominator)
# O = Opted out / optional meeting, blank = no record (ignored entirely)
ATTENDED_CODES = ("P", "L")
COUNTED_CODES = ("P", "L", "A", "Z")
VALID_CODES = ("P", "L", "A", "Z", "O")


# ── Google Sheets connection ────────────────────────────────────────────────

def _get_credentials():
    info = get_secret("gcp_service_account")
    if info:
        return Credentials.from_service_account_info(dict(info), scopes=SCOPES)
    return Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH, scopes=SCOPES)


def get_service_account_email():
    """The email the Google Sheet must be shared with (Editor). None if unknown."""
    try:
        return _get_credentials().service_account_email
    except Exception:
        return None


def _get_worksheet(sheet_id=None):
    """First tab of the configured spreadsheet (or of sheet_id if given)."""
    client = gspread.authorize(_get_credentials())
    return client.open_by_key(sheet_id or get_sheet_id()).sheet1


# ── Parsing ─────────────────────────────────────────────────────────────────

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


def _rows_to_frame(rows):
    """Turn raw sheet rows (list of lists) into a DataFrame with unique headers."""
    if not rows:
        raise ValueError("Empty sheet")
    header = _deduplicate_columns([str(c).strip() for c in rows[0]])
    width = len(header)
    body = [list(r[:width]) + [""] * (width - len(r)) for r in rows[1:]]
    return pd.DataFrame(body, columns=header)


def _process_roster(df):
    """
    Normalise a raw roster frame (from the Sheet or the CSV) into the shape
    every page expects:

        Last Name | First Name | Full Name | Subteam | % Meetings Attended | <date cols>

    Expected input layouts:
        A) Hand-made sheet: Last Name | First Name | % Meetings Attended | dates...
           with subteam names (Executive / Loco / ...) as standalone rows in col 0.
        B) App-written sheet / CSV: a "Subteam" column already exists.

    Section header rows, count rows, blank rows and Coaches are stripped.
    """
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip()
    if len(df.columns) < 2:
        raise ValueError("Roster needs at least a Last Name and a First Name column.")

    # Standardise the first two columns regardless of what the sheet calls them
    df.rename(columns={df.columns[0]: "Last Name", df.columns[1]: "First Name"}, inplace=True)

    # ── Subteam extraction ───────────────────────────────────────────────────
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
        df["Subteam"] = subteams
    elif existing_subteam_col is not None:
        df["Subteam"] = existing_subteam_col
    else:
        df["Subteam"] = None

    # ── Row filtering ────────────────────────────────────────────────────────
    # Remove: section header rows, count/blank rows, coach rows.
    # pd.read_csv turns blank cells into NaN, which astype(str) renders as "nan".
    first_name_col = df["First Name"].fillna("").astype(str).str.strip()
    df = df[
        first_name_col.ne("") &
        first_name_col.str.lower().ne("nan") &
        (~first_name_col.str.isnumeric())
    ].copy()
    df = df[df["Subteam"] != "Coaches"].copy()

    df["Last Name"] = df["Last Name"].fillna("").astype(str).str.strip()
    df["First Name"] = df["First Name"].fillna("").astype(str).str.strip()
    df["Subteam"] = df["Subteam"].where(df["Subteam"].notna(), None)
    df["Full Name"] = df["First Name"] + " " + df["Last Name"]

    # ── % Meetings Attended ──────────────────────────────────────────────────
    if "% Meetings Attended" in df.columns:
        df["% Meetings Attended"] = pd.to_numeric(
            df["% Meetings Attended"].astype(str).str.rstrip("%").str.strip(),
            errors="coerce",
        ).fillna(0.0)
    else:
        df["% Meetings Attended"] = 0.0

    # Blank attendance cells: "" everywhere (never NaN) so isin() checks are uniform
    for c in get_date_columns(df):
        df[c] = df[c].fillna("").astype(str).str.strip()

    return df.reset_index(drop=True)


def load_data():
    """
    Load attendance from the configured Google Sheet, falling back to the
    local CSV backup if the sheet can't be reached.

    The returned frame carries df.attrs["source"] = "sheet" | "csv" so that
    save_data() never pushes a stale CSV back over the live sheet.
    """
    source = "sheet"
    try:
        df = _rows_to_frame(_get_worksheet().get_all_values())
    except Exception as e:
        source = "csv"
        df = pd.read_csv(CSV_PATH, dtype=str)
        st.warning(
            "Couldn't reach the Google Sheet, showing the local backup instead. "
            "Saving is disabled until the sheet is reachable — check the Settings page. "
            f"({type(e).__name__}: {e})"
        )

    df = _process_roster(df)
    df.attrs["source"] = source
    return df


def inspect_sheet(sheet_id):
    """
    Read a spreadsheet and report whether the app can use it — used by the
    Settings page's "Test connection" button. Raises on connection errors.
    """
    ws = _get_worksheet(sheet_id)
    rows = ws.get_all_values()
    raw = _rows_to_frame(rows)
    roster = _process_roster(raw)

    header_rows = raw.iloc[:, 0].astype(str).str.strip().isin(_SUBTEAM_NAMES).any()
    layout = "section headers (hand-made)" if header_rows else "Subteam column (app format)"

    warnings = []
    if roster.empty:
        warnings.append("No members found. Check that rows 2+ have a Last Name and First Name.")
    if roster["Subteam"].isna().any():
        n = int(roster["Subteam"].isna().sum())
        warnings.append(f"{n} member(s) have no subteam. Add section rows or a Subteam column.")
    dupes = roster["Full Name"][roster["Full Name"].duplicated()].unique().tolist()
    if dupes:
        warnings.append(f"Duplicate names: {', '.join(dupes)}. QR codes and Slack matching need unique names.")
    unknown_cols = [
        c for c in raw.columns
        if c not in {"Last Name", "First Name", "Full Name", "Subteam", "% Meetings Attended"}
        and not _DATE_RE.match(c) and c.strip() != ""
    ]
    if unknown_cols:
        warnings.append(f"Ignored columns (not dates): {', '.join(unknown_cols)}")

    return {
        "title": ws.spreadsheet.title,
        "worksheet": ws.title,
        "rows": len(rows),
        "layout": layout,
        "members": int(len(roster)),
        "subteams": roster["Subteam"].dropna().value_counts().to_dict(),
        "date_columns": len(get_date_columns(roster)),
        "warnings": warnings,
    }


# ── Date columns ────────────────────────────────────────────────────────────

def _date_sort_key(col):
    m = _DATE_RE.match(str(col))
    return (datetime.strptime(m.group(1), "%m/%d/%y"), int(m.group(2) or 0))


def get_date_columns(df):
    """
    Return only columns that are meeting dates (MM/DD/YY or MM/DD/YY.N),
    sorted chronologically with same-day sessions in order (.1 after base).

    Sorting matters: backdated entries are appended to the end of the sheet,
    and the prediction model treats column order as the season timeline.
    """
    cols = [c for c in df.columns if _DATE_RE.match(str(c))]
    return sorted(cols, key=_date_sort_key)


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
        .str.replace(r"\.\d+$", "", regex=True)
        .pipe(pd.to_datetime, format="%m/%d/%y", errors="coerce")
    )

    melted["Status"] = melted["Status"].fillna("").astype(str).str.strip()
    melted["Present"] = melted["Status"].isin(ATTENDED_CODES).astype(int)
    melted["Counted"] = melted["Status"].isin(COUNTED_CODES).astype(int)
    return melted


def is_saturday(date_str):
    """True if MM/DD/YY date_str falls on a Saturday (double-session day)."""
    return datetime.strptime(date_str, "%m/%d/%y").weekday() == 5


def get_columns_for_date(df, date_str):
    """
    Return the column name(s) attendance should be written to for a date,
    creating any that don't exist yet (filled with "").

    Saturday meetings are double sessions and count twice, so they get two
    columns: 'MM/DD/YY' and 'MM/DD/YY.1'. All other days get one column.
    """
    cols = [date_str]
    if is_saturday(date_str):
        cols.append(f"{date_str}.1")
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return cols


def write_attendance(df, date_str, present_names, absent_code="A"):
    """
    Record one meeting for the whole roster: everyone in present_names gets
    P, everyone else gets absent_code (A for a regular meeting, O for an
    optional one). Saturday dates are written to both session columns.

    Returns (matched_count, unrecognized_names). Every page that records a
    meeting goes through here so they can't drift apart.
    """
    date_cols = get_columns_for_date(df, date_str)
    present_lower = {str(n).strip().lower() for n in present_names}
    roster_lower = df["Full Name"].str.strip().str.lower()

    is_present = roster_lower.isin(present_lower)
    for c in date_cols:
        df[c] = is_present.map({True: "P", False: absent_code})

    unrecognized = sorted(present_lower - set(roster_lower))
    return int(is_present.sum()), unrecognized


def append_attendance(new_attendance_list):
    """
    Append today's attendance.
    new_attendance_list = ["P", "A", "L", "O", ...] for each member in order.
    """
    df = load_data()
    today_str = datetime.today().strftime("%m/%d/%y")

    if today_str in df.columns:
        print(f"Attendance for {today_str} already exists. Overwriting.")
    for col in get_columns_for_date(df, today_str):
        df[col] = new_attendance_list

    df = recalc_percentages(df)
    save_data(df)


# ── Percentages & saving ────────────────────────────────────────────────────

def recalc_percentages(df):
    """Recalculate % Meetings Attended for each member (P/L over P/L/A/Z)."""
    date_cols = get_date_columns(df)
    if not date_cols:
        df["% Meetings Attended"] = 0.0
        return df
    codes = df[date_cols].fillna("").astype(str).apply(lambda s: s.str.strip())
    attended = codes.isin(ATTENDED_CODES).sum(axis=1)
    counted = codes.isin(COUNTED_CODES).sum(axis=1)
    pct = (attended / counted.where(counted > 0, 1) * 100).where(counted > 0, 0.0).round(2)
    df["% Meetings Attended"] = pct
    return df


def save_data(df, path=None):
    """
    Save to local CSV (backup) and push to the configured Google Sheet.

    If the frame was loaded from the CSV fallback (the sheet was unreachable),
    the sheet push is skipped so stale data can never overwrite the live sheet.
    Returns True if the sheet was updated.
    """
    df = _ordered_columns(df)
    df.to_csv(path or CSV_PATH, index=False)

    if df.attrs.get("source") == "csv":
        st.error(
            "Saved to the local backup only. This data came from the local CSV because "
            "the Google Sheet couldn't be loaded, so it was NOT pushed to the sheet. "
            "Reload the page once the sheet is reachable and re-enter this meeting."
        )
        return False

    try:
        ws = _get_worksheet()
        data = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
        ws.clear()
        ws.update(data)
        return True
    except Exception as e:
        st.warning(f"Saved locally but could not sync to Google Sheet: {e}")
        return False


def _ordered_columns(df):
    """
    Return df with columns in a consistent order:
        Last Name | First Name | Full Name | % Meetings Attended | <dates, chronological> | Subteam
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
    out = df[ordered]
    out.attrs = dict(df.attrs)
    return out
