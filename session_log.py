"""
Check-in / check-out log — deliberately independent of the P/A attendance.

The attendance tab records *expected* attendance: who said on Slack that they
were coming. This log records what actually happened at the door. Nothing here
writes to the attendance tab, and nothing there depends on this; the two are
compared side by side on the admin page and nowhere else.

Two extra tabs in the same spreadsheet:

    Meetings    one row per meeting a mentor opened at the kiosk
    SessionLog  one row per student per meeting, updated on check-out

Writes are append_row / single-cell updates, never a clear-and-rewrite, so
many phones checking in at once can't clobber each other the way the main
attendance save would.
"""
import time
from datetime import datetime, timezone

import gspread
import pandas as pd
import streamlit as st

from data_loader import _get_credentials, SCOPES  # noqa: F401  (SCOPES documents intent)
from settings import get_sheet_id

MEETINGS_TAB = "Meetings"
LOG_TAB = "SessionLog"

MEETING_HEADER = ["meeting_id", "date", "label", "opened_at", "closed_at", "opened_by"]
LOG_HEADER = [
    "meeting_id", "date", "full_name", "check_in_at", "check_out_at",
    "duration_min", "auto_checked_out", "device_id", "flagged", "flag_reason",
]

TIME_FMT = "%Y-%m-%d %H:%M:%S"


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fmt(dt):
    return dt.strftime(TIME_FMT)


def _parse(value):
    try:
        return datetime.strptime(str(value).strip(), TIME_FMT)
    except (TypeError, ValueError):
        return None


def _is_rate_limited(error):
    status = getattr(getattr(error, "response", None), "status_code", None)
    return status in (429, 503)


def _with_retry(call, attempts=3, base_delay=1.0):
    """
    Retry a Sheets call on 429/503 with backoff. A rush at the door can burst
    past the per-minute quota; one retry usually rides it out.
    """
    for attempt in range(attempts):
        try:
            return call()
        except gspread.exceptions.APIError as error:
            if attempt == attempts - 1 or not _is_rate_limited(error):
                raise
            time.sleep(base_delay * (2 ** attempt))


@st.cache_resource(show_spinner=False)
def _open_book(sheet_id):
    """
    Cached spreadsheet handle. Re-opening it per call costs a
    fetch_sheet_metadata request each time, which is most of the read quota.
    """
    return gspread.authorize(_get_credentials()).open_by_key(sheet_id)


def _spreadsheet():
    return _open_book(get_sheet_id())


def _tab(name, header):
    """
    Fetch a tab, creating it with its header row the first time.

    Worksheet handles are cached on the spreadsheet object: gspread's
    .worksheet() re-fetches sheet metadata on every call, and at the kiosk's
    refresh rate that alone would exhaust the read quota.
    """
    book = _spreadsheet()
    cache = getattr(book, "_tab_cache", None)
    if cache is None:
        cache = {}
        try:
            book._tab_cache = cache
        except Exception:
            pass
    if name in cache:
        return cache[name]

    try:
        ws = _with_retry(lambda: book.worksheet(name))
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(title=name, rows=1000, cols=max(len(header), 10))
        ws.update([header])
        cache[name] = ws
        return ws

    if not _with_retry(ws.get_all_values):
        ws.update([header])
    cache[name] = ws
    return ws


def _frame(ws, header):
    rows = _with_retry(ws.get_all_values)
    if len(rows) < 2:
        return pd.DataFrame(columns=header)
    df = pd.DataFrame(rows[1:], columns=rows[0])
    for col in header:
        if col not in df.columns:
            df[col] = ""
    return df


# ── Meetings ────────────────────────────────────────────────────────────────

def open_meeting(opened_by="kiosk", label="", now=None):
    """
    Start a meeting. Check-in only works while one is open, which is also what
    makes auto-checkout possible without a scheduler: closing the meeting is
    the event that closes everyone still inside.
    """
    now = now or _now()
    existing = active_meeting()
    if existing:
        return existing

    ws = _tab(MEETINGS_TAB, MEETING_HEADER)
    meeting_id = now.strftime("%Y%m%d-%H%M%S")
    ws.append_row([meeting_id, now.strftime("%m/%d/%y"), label, _fmt(now), "", opened_by],
                  value_input_option="USER_ENTERED")
    return {"meeting_id": meeting_id, "date": now.strftime("%m/%d/%y"), "label": label,
            "opened_at": _fmt(now), "closed_at": "", "opened_by": opened_by}


def active_meeting():
    """The currently open meeting, or None. Latest open row wins."""
    ws = _tab(MEETINGS_TAB, MEETING_HEADER)
    df = _frame(ws, MEETING_HEADER)
    if df.empty:
        return None
    open_rows = df[df["closed_at"].astype(str).str.strip() == ""]
    if open_rows.empty:
        return None
    return open_rows.iloc[-1].to_dict()


def close_meeting(meeting_id=None, now=None):
    """
    End the meeting and auto-check-out anyone still signed in, marking those
    rows auto_checked_out so you can see who forgot.

    Returns {"closed": n, "auto_checked_out": [names]}.
    """
    now = now or _now()
    meeting = active_meeting()
    if meeting is None:
        return {"closed": 0, "auto_checked_out": []}
    meeting_id = meeting_id or meeting["meeting_id"]

    auto = _close_open_sessions(meeting_id, now, auto=True)

    ws = _tab(MEETINGS_TAB, MEETING_HEADER)
    rows = ws.get_all_values()
    header = rows[0]
    for i, row in enumerate(rows[1:], start=2):
        if row and row[0] == meeting_id:
            ws.update_cell(i, header.index("closed_at") + 1, _fmt(now))
            break
    return {"closed": 1, "auto_checked_out": auto}


# ── Check in / out ──────────────────────────────────────────────────────────

def _close_open_sessions(meeting_id, now, auto=False, only_name=None):
    """Write check_out_at/duration for still-open rows. Returns names closed."""
    ws = _tab(LOG_TAB, LOG_HEADER)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return []
    header = rows[0]
    idx = {c: header.index(c) + 1 for c in header}
    closed = []

    for i, row in enumerate(rows[1:], start=2):
        record = dict(zip(header, row))
        if record.get("meeting_id") != meeting_id:
            continue
        if str(record.get("check_out_at", "")).strip():
            continue
        if only_name is not None and record.get("full_name", "").strip().lower() != only_name:
            continue

        started = _parse(record.get("check_in_at"))
        minutes = int((now - started).total_seconds() // 60) if started else ""
        updates = {"check_out_at": _fmt(now), "duration_min": minutes}
        if auto:
            updates["auto_checked_out"] = "TRUE"
        for col, value in updates.items():
            if col in idx:
                ws.update_cell(i, idx[col], value)
        closed.append(record.get("full_name", ""))

    return closed


def sessions_for(meeting_id):
    """All log rows for one meeting, as a DataFrame."""
    df = _frame(_tab(LOG_TAB, LOG_HEADER), LOG_HEADER)
    if df.empty:
        return df
    return df[df["meeting_id"] == meeting_id].copy()


def open_sessions(meeting_id):
    """Names currently checked in — the kiosk's live 'Signed in: N'."""
    df = sessions_for(meeting_id)
    if df.empty:
        return []
    still_in = df[df["check_out_at"].astype(str).str.strip() == ""]
    return still_in["full_name"].tolist()


def check_in(meeting_id, full_name, device_id="", now=None):
    """
    Record a check-in. One per student per meeting: a second attempt is
    rejected rather than duplicated.

    A device that checks in more than one student in the same meeting gets
    those rows flagged — not blocked, just flagged for a human to look at.
    """
    now = now or _now()
    full_name = str(full_name).strip()
    df = sessions_for(meeting_id)

    if not df.empty and (df["full_name"].str.strip().str.lower() == full_name.lower()).any():
        return {"ok": False, "reason": "already_checked_in"}

    flagged, reason = "", ""
    if device_id and not df.empty:
        others = df[(df["device_id"].astype(str) == str(device_id))
                    & (df["full_name"].str.strip().str.lower() != full_name.lower())]
        if not others.empty:
            flagged, reason = "TRUE", f"same device as {', '.join(sorted(set(others['full_name'])))}"

    ws = _tab(LOG_TAB, LOG_HEADER)
    ws.append_row(
        [meeting_id, now.strftime("%m/%d/%y"), full_name, _fmt(now), "", "", "",
         str(device_id or ""), flagged, reason],
        value_input_option="USER_ENTERED",
    )
    return {"ok": True, "flagged": bool(flagged), "flag_reason": reason}


def check_out(meeting_id, full_name, now=None):
    """Close a student's open session. Returns ok=False if they weren't in."""
    now = now or _now()
    name = str(full_name).strip().lower()
    df = sessions_for(meeting_id)
    if df.empty:
        return {"ok": False, "reason": "not_checked_in"}

    mine = df[df["full_name"].str.strip().str.lower() == name]
    if mine.empty:
        return {"ok": False, "reason": "not_checked_in"}
    if (mine["check_out_at"].astype(str).str.strip() != "").all():
        return {"ok": False, "reason": "already_checked_out"}

    closed = _close_open_sessions(meeting_id, now, auto=False, only_name=name)
    return {"ok": bool(closed), "reason": "" if closed else "not_checked_in"}


def manual_override(meeting_id, full_name, direction, now=None):
    """Mentor-operated check in/out for a dead phone. Bypasses the code only."""
    if direction == "in":
        return check_in(meeting_id, full_name, device_id="mentor", now=now)
    return check_out(meeting_id, full_name, now=now)


def recent_meetings(limit=20):
    df = _frame(_tab(MEETINGS_TAB, MEETING_HEADER), MEETING_HEADER)
    return df.tail(limit).iloc[::-1] if not df.empty else df


def all_sessions():
    return _frame(_tab(LOG_TAB, LOG_HEADER), LOG_HEADER)
