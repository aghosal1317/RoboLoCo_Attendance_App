"""
Kiosk, student check-in, and check-in admin, driven through AppTest.
"""
import os
import sys
from datetime import datetime

import pytest
from streamlit.testing.v1 import AppTest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import data_loader as dl          # noqa: E402
import rotating_code as rc        # noqa: E402
import session_log as sl          # noqa: E402
import streamlit as st            # noqa: E402

T0 = datetime(2026, 11, 9, 17, 0, 0)


def _run(page, **state):
    at = AppTest.from_file(f"pages/{page}", default_timeout=30)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def _no_exceptions(at):
    assert not at.exception, [e.value for e in at.exception]


@pytest.fixture(autouse=True)
def _isolate(fake_ws, fake_book, tmp_paths, monkeypatch):
    monkeypatch.setattr(rc, "get_secret",
                        lambda k, d=None: {"CHECKIN_SECRET": "test-secret"}.get(k, d))
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture
def meeting(fake_book):
    return sl.open_meeting(opened_by="kiosk", label="Test", now=T0)


def code(direction, meeting_id):
    return rc.current_code(direction, meeting_id, secret="test-secret")


# ── kiosk ───────────────────────────────────────────────────────────────────

def test_kiosk_requires_the_pin():
    at = _run("11_kiosk.py")
    _no_exceptions(at)
    assert [t.label for t in at.text_input] == ["Kiosk PIN"]
    # no codes on screen before unlocking
    assert not any("CHECK IN" in m.value for m in at.markdown)


def test_kiosk_rejects_a_wrong_pin():
    at = _run("11_kiosk.py")
    at.text_input[0].set_value("0000")
    at.button[0].click().run()
    assert any("Wrong PIN" in e.value for e in at.error)
    assert "kiosk_unlocked" not in at.session_state


def test_kiosk_unlocks_with_the_right_pin():
    at = _run("11_kiosk.py")
    at.text_input[0].set_value("5338")
    at.button[0].click().run()
    _no_exceptions(at)
    assert at.session_state["kiosk_unlocked"] is True


def test_kiosk_offers_to_start_a_meeting_when_none_is_open(fake_book):
    at = _run("11_kiosk.py", kiosk_unlocked=True)
    _no_exceptions(at)
    assert any("No meeting is open" in w.value for w in at.warning)
    assert any(b.label == "Start meeting" for b in at.button)


def test_kiosk_starting_a_meeting_shows_both_codes(fake_book):
    at = _run("11_kiosk.py", kiosk_unlocked=True)
    [b for b in at.button if b.label == "Start meeting"][0].click().run()
    _no_exceptions(at)
    rendered = " ".join(m.value for m in at.markdown)
    assert "CHECK IN" in rendered and "CHECK OUT" in rendered
    assert "Signed in:" in rendered

    mid = sl.active_meeting()["meeting_id"]
    assert code("in", mid) in rendered
    assert code("out", mid) in rendered


def test_kiosk_warns_when_the_secret_is_not_configured(monkeypatch, fake_book):
    monkeypatch.setattr(rc, "get_secret", lambda k, d=None: d)
    at = _run("11_kiosk.py", kiosk_unlocked=True)
    assert any("CHECKIN_SECRET is not set" in e.value for e in at.error)


def test_kiosk_end_meeting_auto_checks_out(fake_book, meeting):
    sl.check_in(meeting["meeting_id"], "Eshan Nayak", now=T0)
    at = _run("11_kiosk.py", kiosk_unlocked=True)
    [b for b in at.button if b.label == "End meeting"][0].click().run()
    _no_exceptions(at)
    assert any("checked out automatically" in s.value for s in at.success)
    assert sl.active_meeting() is None


# ── student check-in ────────────────────────────────────────────────────────

def test_checkin_closed_when_no_meeting_is_open(fake_book):
    at = _run("12_checkin.py")
    _no_exceptions(at)
    assert any("No meeting is open" in i.value for i in at.info)
    assert not at.text_input


def test_checkin_needs_a_name_before_a_code(fake_book, meeting):
    at = _run("12_checkin.py")
    _no_exceptions(at)
    assert at.selectbox[0].value == ""
    assert not at.text_input          # code box only appears after a name


def test_checkin_with_the_right_code_signs_you_in(fake_book, meeting):
    mid = meeting["meeting_id"]
    at = _run("12_checkin.py")
    at.selectbox[0].set_value("Eshan Nayak").run()
    at.text_input[0].set_value(code("in", mid)).run()
    [b for b in at.button if b.label == "Check in"][0].click().run()
    _no_exceptions(at)

    assert any("Checked in" in s.value for s in at.success)
    assert sl.open_sessions(mid) == ["Eshan Nayak"]


def test_checkin_with_a_wrong_code_is_refused(fake_book, meeting):
    mid = meeting["meeting_id"]
    wrong = f"{(int(code('in', mid)) + 7) % 10000:04d}"
    at = _run("12_checkin.py")
    at.selectbox[0].set_value("Eshan Nayak").run()
    at.text_input[0].set_value(wrong).run()
    [b for b in at.button if b.label == "Check in"][0].click().run()
    _no_exceptions(at)

    assert any("Code expired" in e.value for e in at.error)
    assert sl.open_sessions(mid) == []


def test_the_check_out_code_cannot_be_used_to_check_in(fake_book, meeting):
    """A forwarded check-out code must not let someone sign in from home."""
    mid = meeting["meeting_id"]
    at = _run("12_checkin.py")
    at.selectbox[0].set_value("Eshan Nayak").run()
    at.text_input[0].set_value(code("out", mid)).run()
    [b for b in at.button if b.label == "Check in"][0].click().run()
    assert any("Code expired" in e.value for e in at.error)
    assert sl.open_sessions(mid) == []


def test_check_out_requires_the_check_out_code(fake_book, meeting):
    mid = meeting["meeting_id"]
    sl.check_in(mid, "Eshan Nayak", now=T0)

    at = _run("12_checkin.py")
    at.selectbox[0].set_value("Eshan Nayak").run()
    assert any("You're checked in" in s.value for s in at.success)

    # the check-in code must not work for checking out
    at.text_input[0].set_value(code("in", mid)).run()
    [b for b in at.button if b.label == "Check out"][0].click().run()
    assert any("Code expired" in e.value for e in at.error)
    assert sl.open_sessions(mid) == ["Eshan Nayak"]

    # the right one does
    at.text_input[0].set_value(code("out", mid)).run()
    [b for b in at.button if b.label == "Check out"][0].click().run()
    _no_exceptions(at)
    assert any("Checked out" in s.value for s in at.success)
    assert sl.open_sessions(mid) == []


def test_checking_in_twice_is_refused(fake_book, meeting):
    mid = meeting["meeting_id"]
    sl.check_in(mid, "Eshan Nayak", now=T0)
    at = _run("12_checkin.py")
    at.selectbox[0].set_value("Eshan Nayak").run()
    # already in, so the page offers check-out rather than a second check-in
    assert not any(b.label == "Check in" for b in at.button)
    assert any(b.label == "Check out" for b in at.button)


# ── admin ───────────────────────────────────────────────────────────────────

def test_admin_requires_login(fake_book, meeting):
    at = _run("13_checkin_admin.py")
    _no_exceptions(at)
    assert [t.label for t in at.text_input] == ["Username", "Password"]


def test_admin_lists_flagged_and_auto_checked_out(fake_book, meeting):
    mid = meeting["meeting_id"]
    sl.check_in(mid, "Eshan Nayak", device_id="phone-1", now=T0)
    sl.check_in(mid, "JD Queen", device_id="phone-1", now=T0)      # same phone -> flagged
    sl.close_meeting(mid, now=datetime(2026, 11, 9, 19, 0, 0))     # both auto-checked-out

    at = _run("13_checkin_admin.py", admin_authed=True)
    _no_exceptions(at)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Checked in"] == "2"
    assert metrics["Flagged"] == "1"
    assert metrics["Forgot to check out"] == "2"


def test_admin_compares_said_versus_showed(fake_book, fake_ws, meeting, monkeypatch):
    """The point of the system: RSVP from Slack vs who actually walked in."""
    mid = meeting["meeting_id"]
    date_str = meeting["date"]
    # Eshan said P and showed; JD said P and didn't; Julia showed unexpectedly.
    fake_ws.rows = [
        ["Last Name", "First Name", "Full Name", "Subteam", "% Meetings Attended", date_str],
        ["Nayak", "Eshan", "Eshan Nayak", "Loco", "", "P"],
        ["Queen", "JD", "JD Queen", "Loco", "", "P"],
        ["Miller", "Julia", "Julia Miller", "Loco", "", "A"],
    ]
    sl.check_in(mid, "Eshan Nayak", now=T0)
    sl.check_in(mid, "Julia Miller", now=T0)

    at = _run("13_checkin_admin.py", admin_authed=True)
    _no_exceptions(at)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Said yes, didn't show"] == "1"      # JD
    assert metrics["Showed, wasn't expected"] == "1"    # Julia
    assert metrics["Said yes and showed"] == "1"        # Eshan


def test_admin_manual_check_in_needs_no_code(fake_book, meeting):
    at = _run("13_checkin_admin.py", admin_authed=True)
    at.selectbox[1].set_value("Eshan Nayak").run()
    [b for b in at.button if b.label == "Check in"][0].click().run()
    _no_exceptions(at)
    assert sl.open_sessions(meeting["meeting_id"]) == ["Eshan Nayak"]
