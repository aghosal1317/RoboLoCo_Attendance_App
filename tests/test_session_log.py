"""
The check-in log. Deliberately independent of the P/A attendance tab —
these tests also pin that it never writes there.
"""
from datetime import datetime, timedelta

import pytest

import session_log as sl

T0 = datetime(2026, 11, 9, 17, 0, 0)


def mins(n):
    """n minutes after T0 — works past the hour, unlike a raw minute field."""
    return T0 + timedelta(minutes=n)


@pytest.fixture
def meeting(fake_book):
    return sl.open_meeting(opened_by="kiosk", label="Test", now=T0)


# ── meetings ────────────────────────────────────────────────────────────────

def test_open_meeting_creates_tabs_with_headers(fake_book, meeting):
    assert sl.MEETINGS_TAB in fake_book.tabs
    assert fake_book.tabs[sl.MEETINGS_TAB].rows[0] == sl.MEETING_HEADER
    assert meeting["meeting_id"] == "20261109-170000"
    assert meeting["date"] == "11/09/26"


def test_active_meeting_found_then_cleared(fake_book, meeting):
    assert sl.active_meeting()["meeting_id"] == meeting["meeting_id"]
    sl.close_meeting(meeting["meeting_id"], now=mins(30))
    assert sl.active_meeting() is None


def test_opening_twice_returns_the_same_meeting(fake_book, meeting):
    again = sl.open_meeting(now=mins(5))
    assert again["meeting_id"] == meeting["meeting_id"]
    assert len(fake_book.tabs[sl.MEETINGS_TAB].rows) == 2   # header + one meeting


def test_no_meeting_means_none(fake_book):
    assert sl.active_meeting() is None


# ── check in ────────────────────────────────────────────────────────────────

def test_check_in_records_a_row(fake_book, meeting):
    mid = meeting["meeting_id"]
    assert sl.check_in(mid, "Eshan Nayak", device_id="dev1", now=mins(2))["ok"]
    df = sl.sessions_for(mid)
    assert df["full_name"].tolist() == ["Eshan Nayak"]
    assert df["check_in_at"].iloc[0] == "2026-11-09 17:02:00"
    assert df["check_out_at"].iloc[0] == ""


def test_one_check_in_per_student_per_meeting(fake_book, meeting):
    mid = meeting["meeting_id"]
    sl.check_in(mid, "Eshan Nayak", now=mins(2))
    second = sl.check_in(mid, "eshan nayak", now=mins(3))
    assert second == {"ok": False, "reason": "already_checked_in"}
    assert len(sl.sessions_for(mid)) == 1


def test_open_sessions_tracks_who_is_in(fake_book, meeting):
    mid = meeting["meeting_id"]
    sl.check_in(mid, "A One", now=mins(1))
    sl.check_in(mid, "B Two", now=mins(2))
    assert sorted(sl.open_sessions(mid)) == ["A One", "B Two"]
    sl.check_out(mid, "A One", now=mins(50))
    assert sl.open_sessions(mid) == ["B Two"]


# ── check out ───────────────────────────────────────────────────────────────

def test_check_out_records_time_and_duration(fake_book, meeting):
    mid = meeting["meeting_id"]
    sl.check_in(mid, "A One", now=mins(0))
    assert sl.check_out(mid, "A One", now=mins(45))["ok"]
    row = sl.sessions_for(mid).iloc[0]
    assert row["check_out_at"] == "2026-11-09 17:45:00"
    assert str(row["duration_min"]) == "45"
    assert row["auto_checked_out"] == ""


def test_check_out_without_check_in_is_refused(fake_book, meeting):
    assert sl.check_out(meeting["meeting_id"], "Nobody", now=mins(5)) == \
        {"ok": False, "reason": "not_checked_in"}


def test_double_check_out_is_refused(fake_book, meeting):
    mid = meeting["meeting_id"]
    sl.check_in(mid, "A One", now=mins(0))
    sl.check_out(mid, "A One", now=mins(30))
    assert sl.check_out(mid, "A One", now=mins(40))["reason"] == "already_checked_out"


# ── auto checkout ───────────────────────────────────────────────────────────

def test_closing_a_meeting_auto_checks_out_whoever_is_left(fake_book, meeting):
    mid = meeting["meeting_id"]
    sl.check_in(mid, "Left Early", now=mins(0))
    sl.check_in(mid, "Forgot", now=mins(0))
    sl.check_out(mid, "Left Early", now=mins(30))

    result = sl.close_meeting(mid, now=mins(120))
    assert result["auto_checked_out"] == ["Forgot"]

    df = sl.sessions_for(mid).set_index("full_name")
    assert df.loc["Forgot", "auto_checked_out"] == "TRUE"
    assert df.loc["Forgot", "check_out_at"] == "2026-11-09 19:00:00"
    assert str(df.loc["Forgot", "duration_min"]) == "120"
    assert df.loc["Left Early", "auto_checked_out"] == ""    # they did it properly


def test_closing_with_nobody_left_is_quiet(fake_book, meeting):
    result = sl.close_meeting(meeting["meeting_id"], now=mins(60))
    assert result == {"closed": 1, "auto_checked_out": []}


# ── device flagging ─────────────────────────────────────────────────────────

def test_one_phone_two_students_is_flagged_not_blocked(fake_book, meeting):
    mid = meeting["meeting_id"]
    first = sl.check_in(mid, "A One", device_id="phone-1", now=mins(1))
    second = sl.check_in(mid, "B Two", device_id="phone-1", now=mins(2))

    assert first["flagged"] is False
    assert second["ok"] is True          # not blocked
    assert second["flagged"] is True
    assert "A One" in second["flag_reason"]
    assert len(sl.sessions_for(mid)) == 2


def test_separate_phones_are_not_flagged(fake_book, meeting):
    mid = meeting["meeting_id"]
    sl.check_in(mid, "A One", device_id="phone-1", now=mins(1))
    assert sl.check_in(mid, "B Two", device_id="phone-2", now=mins(2))["flagged"] is False


def test_missing_device_id_never_flags(fake_book, meeting):
    """Cookies can be unavailable; that must not accuse anyone."""
    mid = meeting["meeting_id"]
    sl.check_in(mid, "A One", device_id="", now=mins(1))
    assert sl.check_in(mid, "B Two", device_id="", now=mins(2))["flagged"] is False


def test_same_phone_in_a_later_meeting_is_not_flagged(fake_book, meeting):
    """A student reusing their own phone next week is not suspicious."""
    mid = meeting["meeting_id"]
    sl.check_in(mid, "A One", device_id="phone-1", now=mins(1))
    sl.close_meeting(mid, now=mins(120))
    later = sl.open_meeting(now=datetime(2026, 11, 11, 17, 0, 0))
    assert sl.check_in(later["meeting_id"], "A One", device_id="phone-1",
                       now=datetime(2026, 11, 11, 17, 5, 0))["flagged"] is False


# ── independence from the attendance tab ────────────────────────────────────

def test_nothing_here_touches_the_attendance_tab(fake_book, fake_ws, meeting):
    mid = meeting["meeting_id"]
    before = [list(r) for r in fake_ws.rows]
    sl.check_in(mid, "Eshan Nayak", device_id="d", now=mins(1))
    sl.check_out(mid, "Eshan Nayak", now=mins(40))
    sl.close_meeting(mid, now=mins(120))
    assert fake_ws.rows == before
    assert fake_ws.updates == [] and fake_ws.cleared == 0


def test_manual_override_works_without_a_code(fake_book, meeting):
    mid = meeting["meeting_id"]
    assert sl.manual_override(mid, "Dead Phone", "in", now=mins(5))["ok"]
    assert sl.open_sessions(mid) == ["Dead Phone"]
    assert sl.manual_override(mid, "Dead Phone", "out", now=mins(60))["ok"]
    assert sl.open_sessions(mid) == []
