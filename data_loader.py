import pandas as pd
from datetime import datetime

CSV_PATH = "data/attendance.csv"


def load_data():
    """Load and clean attendance CSV."""
    df = pd.read_csv(CSV_PATH)
    df.columns = df.columns.str.strip()

    # Rename first two columns
    df.rename(columns={
        df.columns[0]: "Last Name",
        df.columns[1]: "First Name"
    }, inplace=True)

    # Extract Subteam from Last Name column
    subteam = None
    subteams = []
    for val in df["Last Name"]:
        if val in ["Executive", "Loco", "Mechanical", "Software", "Coaches"]:
            subteam = val
            subteams.append(None)
        else:
            subteams.append(subteam)
    df["Subteam"] = subteams

    # Remove section header rows
    df = df[df["First Name"].notna()]

    # Clean % Meetings Attended
    if "% Meetings Attended" in df.columns:
        df["% Meetings Attended"] = (
            df["% Meetings Attended"].astype(str).str.rstrip("%").astype(float)
        )
    else:
        df["% Meetings Attended"] = 0.0

    return df


def get_date_columns(df):
    """Return list of columns that are actual dates."""
    skip = {"Subteam", "Last Name", "First Name", "% Meetings Attended"}
    return [c for c in df.columns if c not in skip]


def melt_attendance(df):
    """Convert wide attendance table to long format for analysis."""
    melted = df.melt(
        id_vars=["First Name", "Last Name", "Subteam"],
        var_name="Date",
        value_name="Status"
    )

    # Keep only date columns
    melted = melted[melted["Date"].str.contains(r"\d{2}/\d{2}/\d{2}", na=False)]

    # Convert to datetime
    melted["Date"] = pd.to_datetime(melted["Date"], format="%m/%d/%y", errors="coerce")
    # Only 'P' counts as present
    melted["Present"] = (melted["Status"] == "P").astype(int)

    return melted


def append_attendance(new_attendance_list):
    """
    Append today's attendance.
    new_attendance_list = ["P", "A", "L", "O", ...] for each member in order
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
        statuses = [row[c] for c in date_cols if row[c] in ["P", "L"]]
        total_meetings = [row[c] for c in date_cols if row[c] in ["P", "L", "A", "Z"]]
        if total_meetings:
            df.at[i, "% Meetings Attended"] = round(len(statuses) / len(total_meetings) * 100, 2)
        else:
            df.at[i, "% Meetings Attended"] = 0.0
    return df


def save_data(df, path=CSV_PATH):
    """Save CSV."""
    df.to_csv(path, index=False)