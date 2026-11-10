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
import threading
import time
from datetime import datetime, timezone

import gspread
import pandas as pd
import streamlit as st

from data_loader import _get_credentials, SCOPES  # noqa: F401  (SCOPES documents intent)
from settings import get_sheet_id

MEETINGS_TAB = "Meetings"
LOG_TAB = "SessionLog"
HOURS_TAB = "Hours"

MEETING_HEADER = ["meeting_id", "date", "label", "opened_at", "closed_at", "opened_by"]
LOG_HEADER = [
    "meeting_id", "date", "full_name", "check_in_at", "check_out_at",
    "duration_min", "auto_checked_out", "device_id", "flagged", "flag_reason",
]

HOURS_HEADER = [
    "full_name", "date", "meeting_id", "check_in_at", "check_out_at",
    "minutes", "hours", "auto_checked_out",
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


# One Streamlit server shares st.cache_data across every visitor, so a cached
# read serves the whole team from a single API call. Without this, each student
# costs ~8 reads (Streamlit reruns the script on every keystroke and click)
# against a 60/min quota — about 7 students a minute before it errors.
CACHE_SECONDS = 15

_HEADERS = {}          # filled in below, once the headers exist


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def _cached_values(sheet_id, tab_name):
    """Raw rows for a tab, shared by everyone for CACHE_SECONDS."""
    return _with_retry(_tab(tab_name, _HEADERS[tab_name]).get_all_values)


def _values(tab_name, cached=False):
    if cached:
        return _cached_values(get_sheet_id(), tab_name)
    return _with_retry(_tab(tab_name, _HEADERS[tab_name]).get_all_values)


def invalidate_cache():
    """Drop the shared read cache — used when a mentor opens or closes a meeting."""
    try:
        _cached_values.clear()
    except Exception:
        pass


def _frame_from(rows, header):
    if len(rows) < 2:
        return pd.DataFrame(columns=header)
    df = pd.DataFrame(rows[1:], columns=rows[0])
    for col in header:
        if col not in df.columns:
            df[col] = ""
    return df


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

def _tab_frame(tab_name, cached=False):
    return _frame_from(_values(tab_name, cached=cached), _HEADERS[tab_name])


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
    invalidate_cache()
    return {"meeting_id": meeting_id, "date": now.strftime("%m/%d/%y"), "label": label,
            "opened_at": _fmt(now), "closed_at": "", "opened_by": opened_by}


def active_meeting(cached=False):
    """
    The currently open meeting, or None. Latest open row wins.
    Pages pass cached=True; anything that then writes reads fresh.
    """
    df = _tab_frame(MEETINGS_TAB, cached=cached)
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
    try:
        flush_pending()          # don't close a meeting with check-ins still queued
    except Exception:
        pass
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

    # Durations are final once the meeting is closed, so refresh the Hours tab.
    # A failure here must not lose the close itself.
    try:
        rebuild_hours_tab()
    except Exception:
        pass

    invalidate_cache()
    return {"closed": 1, "auto_checked_out": auto}


# ── Batching writes ─────────────────────────────────────────────────────────
#
# Writes are the ceiling: Google allows ~60/minute for the whole app. Two things
# used to blow through it — a check-in costing one append each, and closing a
# meeting costing three cell updates per person still signed in (228 writes for
# a team of 76, which simply fails).
#
# Check-ins are coalesced instead. Each one queues its row and then tries to
# flush; only one thread flushes at a time, so anything queued while a flush is
# in flight goes out together in the next one. Under a rush that turns dozens of
# appends into a couple of calls, and when it's quiet each check-in still writes
# immediately — there is no timer, so nothing sits unwritten waiting for one.

_pending_rows = []
_pending_lock = threading.Lock()
_flush_lock = threading.Lock()


def _column_letter(index):
    """1 -> A, 27 -> AA."""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _batch_set_cells(ws, updates):
    """
    Apply [(row, col, value), ...] in ONE API call instead of one per cell.
    Falls back to update_cell if the worksheet has no batch_update.
    """
    if not updates:
        return 0
    if not hasattr(ws, "batch_update"):
        for row, col, value in updates:
            _with_retry(lambda r=row, c=col, v=value: ws.update_cell(r, c, v))
        return len(updates)

    body = [{"range": f"{_column_letter(col)}{row}", "values": [[value]]}
            for row, col, value in updates]
    _with_retry(lambda: ws.batch_update(body, value_input_option="USER_ENTERED"))
    return 1


def _queue_row(row):
    with _pending_lock:
        _pending_rows.append(row)


def flush_pending(force=False):
    """
    Write everything queued. Returns how many rows went out. Safe to call from
    anywhere; if another thread is already flushing, this one simply returns
    once that flush has covered its row.
    """
    acquired = _flush_lock.acquire(blocking=True, timeout=10)
    if not acquired:
        return 0
    try:
        with _pending_lock:
            batch = _pending_rows[:]
            _pending_rows.clear()
        if not batch:
            return 0
        try:
            ws = _tab(LOG_TAB, LOG_HEADER)
            _with_retry(lambda: ws.append_rows(batch, value_input_option="USER_ENTERED"))
        except Exception:
            with _pending_lock:                 # put them back; nothing is lost
                _pending_rows[:0] = batch
            raise
        return len(batch)
    finally:
        _flush_lock.release()


def pending_count():
    with _pending_lock:
        return len(_pending_rows)


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

    cell_updates = []
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
                cell_updates.append((i, idx[col], value))
        closed.append(record.get("full_name", ""))

    # One call for the whole meeting rather than three per person: closing a
    # meeting of 76 was 228 writes, well past the per-minute quota.
    _batch_set_cells(ws, cell_updates)
    return closed


def _flush_quietly():
    try:
        flush_pending()
    except Exception:
        pass


def sessions_for(meeting_id, cached=False):
    """
    Log rows for one meeting. Duplicates are collapsed to the first check-in
    per member: the hot path checks for an existing check-in against a cached
    read, so a double-tap within the cache window can append twice. Deduping
    here keeps headcounts and hours right regardless.
    """
    if not cached:
        _flush_quietly()         # a fresh read must include anything still queued
    df = _tab_frame(LOG_TAB, cached=cached)
    if df.empty:
        return df
    mine = df[df["meeting_id"] == meeting_id].copy()
    if mine.empty:
        return mine
    key = mine["full_name"].astype(str).str.strip().str.lower()
    return mine[~key.duplicated(keep="first")].copy()


def open_sessions(meeting_id, cached=False):
    """Names currently checked in — the kiosk's live 'Signed in: N'."""
    df = sessions_for(meeting_id, cached=cached)
    if df.empty:
        return []
    still_in = df[df["check_out_at"].astype(str).str.strip() == ""]
    return still_in["full_name"].tolist()


def check_in(meeting_id, full_name, device_id="", now=None, sessions=None):
    """
    Record a check-in. One per student per meeting: a second attempt is
    rejected rather than duplicated.

    A device that checks in more than one student in the same meeting gets
    those rows flagged — not blocked, just flagged for a human to look at.
    """
    now = now or _now()
    full_name = str(full_name).strip()
    # The page already read the log to render the form; reusing that frame keeps
    # a check-in at one API call (the append) instead of a read plus an append.
    df = sessions_for(meeting_id) if sessions is None else sessions

    if not df.empty and (df["full_name"].str.strip().str.lower() == full_name.lower()).any():
        return {"ok": False, "reason": "already_checked_in"}

    flagged, reason = "", ""
    if device_id and not df.empty:
        others = df[(df["device_id"].astype(str) == str(device_id))
                    & (df["full_name"].str.strip().str.lower() != full_name.lower())]
        if not others.empty:
            flagged, reason = "TRUE", f"same device as {', '.join(sorted(set(others['full_name'])))}"

    _queue_row([meeting_id, now.strftime("%m/%d/%y"), full_name, _fmt(now), "", "", "",
                str(device_id or ""), flagged, reason])
    flush_pending()
    return {"ok": True, "flagged": bool(flagged), "flag_reason": reason}


def check_out(meeting_id, full_name, now=None, sessions=None):
    """Close a student's open session. Returns ok=False if they weren't in."""
    now = now or _now()
    name = str(full_name).strip().lower()
    df = sessions_for(meeting_id) if sessions is None else sessions
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
    df = _tab_frame(MEETINGS_TAB)
    return df.tail(limit).iloc[::-1] if not df.empty else df


def all_sessions():
    """Every log row, duplicates collapsed per member per meeting."""
    df = _tab_frame(LOG_TAB)
    if df.empty:
        return df
    key = (df["meeting_id"].astype(str) + "|"
           + df["full_name"].astype(str).str.strip().str.lower())
    return df[~key.duplicated(keep="first")].copy()


_HEADERS.update({
    MEETINGS_TAB: MEETING_HEADER,
    LOG_TAB: LOG_HEADER,
    HOURS_TAB: HOURS_HEADER,
})


# ── Hours ───────────────────────────────────────────────────────────────────

def _duration_minutes(row):
    """
    Minutes between check-in and check-out, recomputed from the timestamps
    rather than trusting the stored value, which can be stale after a manual
    fix-up. None while a session is still open.
    """
    started, ended = _parse(row.get("check_in_at")), _parse(row.get("check_out_at"))
    if started is None or ended is None:
        return None
    minutes = int((ended - started).total_seconds() // 60)
    return max(minutes, 0)


def hours_rows():
    """
    One row per session, with its length — the raw list behind the Hours tab.
    Sessions still open have blank minutes/hours and are excluded from totals.
    """
    df = all_sessions()
    if df.empty:
        return pd.DataFrame(columns=HOURS_HEADER)

    out = []
    for _, row in df.iterrows():
        minutes = _duration_minutes(row)
        out.append({
            "full_name": str(row.get("full_name", "")).strip(),
            "date": row.get("date", ""),
            "meeting_id": row.get("meeting_id", ""),
            "check_in_at": row.get("check_in_at", ""),
            "check_out_at": row.get("check_out_at", ""),
            "minutes": "" if minutes is None else minutes,
            "hours": "" if minutes is None else round(minutes / 60, 2),
            "auto_checked_out": row.get("auto_checked_out", ""),
        })

    frame = pd.DataFrame(out, columns=HOURS_HEADER)
    return frame.sort_values(["full_name", "check_in_at"]).reset_index(drop=True)


def member_totals():
    """
    Total time per member across every meeting they checked in and out of.
    Columns: full_name | meetings | minutes | hours | still_open | auto_closed
    """
    rows = hours_rows()
    if rows.empty:
        return pd.DataFrame(columns=["full_name", "meetings", "minutes", "hours",
                                     "still_open", "auto_closed"])

    done = rows[rows["minutes"] != ""].copy()
    done["minutes"] = done["minutes"].astype(int)

    totals = (
        done.groupby("full_name")
        .agg(meetings=("minutes", "size"), minutes=("minutes", "sum"))
        .reset_index()
    )
    totals["hours"] = (totals["minutes"] / 60).round(2)

    open_counts = (rows[rows["minutes"] == ""].groupby("full_name").size()
                   .rename("still_open").reset_index())
    auto_counts = (done[done["auto_checked_out"].astype(str).str.upper() == "TRUE"]
                   .groupby("full_name").size().rename("auto_closed").reset_index())

    totals = totals.merge(open_counts, on="full_name", how="outer")
    totals = totals.merge(auto_counts, on="full_name", how="outer")
    for col in ("meetings", "minutes", "still_open", "auto_closed"):
        totals[col] = totals[col].fillna(0).astype(int)
    totals["hours"] = totals["hours"].fillna(0.0)

    return totals.sort_values("minutes", ascending=False).reset_index(drop=True)


def total_hours():
    """Grand total across everyone: (hours, minutes, sessions counted)."""
    rows = hours_rows()
    if rows.empty:
        return {"hours": 0.0, "minutes": 0, "sessions": 0}
    done = rows[rows["minutes"] != ""]
    minutes = int(done["minutes"].astype(int).sum())
    return {"hours": round(minutes / 60, 2), "minutes": minutes, "sessions": len(done)}


def rebuild_hours_tab():
    """
    Recompute the Hours tab from the log. It is derived data that nothing else
    writes, so overwriting the whole tab is safe — unlike the attendance tab.
    Called automatically when a meeting is closed, and from the Hours page.
    """
    rows = hours_rows()
    ws = _tab(HOURS_TAB, HOURS_HEADER)
    data = [HOURS_HEADER] + rows.astype(str).values.tolist()
    _with_retry(ws.clear)
    _with_retry(lambda: ws.update(data))
    return len(rows)
