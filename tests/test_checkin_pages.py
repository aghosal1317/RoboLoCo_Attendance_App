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

import conftest                   # noqa: E402
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


def _fake_response(status):
    """A response object shaped enough like requests' for gspread.APIError."""
    class Resp:
        status_code = status
        text = f"{status} error"

        def json(self):
            return {"error": {"code": status, "message": "Quota exceeded",
                              "status": "RESOURCE_EXHAUSTED"}}

    return Resp


# ── API budget: the kiosk refreshes every second and must not spend quota ───

class CountingWorksheet(conftest.FakeWorksheet):
    """Counts the calls that cost a Google Sheets API request."""

    def __init__(self, *a, counter=None, **kw):
        super().__init__(*a, **kw)
        self.counter = counter if counter is not None else {"reads": 0}

    def get_all_values(self):
        self.counter["reads"] += 1
        return super().get_all_values()


class CountingBook(conftest.FakeSpreadsheet):
    def __init__(self, title="Fake", counter=None):
        super().__init__(title, tabs={})
        self.counter = counter if counter is not None else {"reads": 0, "opens": 0}

    def worksheet(self, name):
        import gspread
        if name not in self.tabs:
            raise gspread.WorksheetNotFound(name)
        self.counter["reads"] += 1          # gspread refetches metadata here
        return self.tabs[name]

    def add_worksheet(self, title, rows=100, cols=20):
        ws = CountingWorksheet([], title=title, counter=self.counter)
        ws.spreadsheet = self
        self.tabs[title] = ws
        return ws


@pytest.fixture
def counting_book(monkeypatch):
    counter = {"reads": 0, "opens": 0}
    book = CountingBook(counter=counter)

    def _open():
        counter["opens"] += 1
        return book

    monkeypatch.setattr(sl, "_spreadsheet", _open)
    return book, counter


def test_code_display_makes_no_api_calls(counting_book):
    """
    Regression: the kiosk's 1-second fragment used to read the log for the
    headcount, which is ~120 requests/minute against a 60/minute quota. It
    rate-limited the kiosk and every student's phone with it. The codes are
    pure HMAC, so the fast fragment must touch the API zero times.
    """
    book, counter = counting_book
    sl.open_meeting(now=T0)
    mid = sl.active_meeting()["meeting_id"]
    baseline = dict(counter)          # after setup; the loop below must add nothing

    for _ in range(60):                       # a minute of countdown ticks
        rc.current_code("in", mid, secret="test-secret")
        rc.current_code("out", mid, secret="test-secret")
        rc.seconds_remaining()

    assert counter["reads"] == baseline["reads"]
    assert counter["opens"] == baseline["opens"]


def test_kiosk_headcount_refresh_is_slow_enough_for_the_quota():
    import re
    kiosk_src = open(os.path.join(ROOT, "pages", "11_kiosk.py")).read()
    # the fast fragment must not read sessions; the slow one must stay under quota
    assert "@st.fragment(run_every=1)" in kiosk_src
    assert "run_every=SIGNED_IN_REFRESH_SECONDS" in kiosk_src
    fast = kiosk_src.split("@st.fragment(run_every=1)")[1].split("@st.fragment")[0]
    assert "open_sessions" not in fast, "the 1s fragment must make no API calls"

    seconds = int(re.search(r"SIGNED_IN_REFRESH_SECONDS = (\d+)", kiosk_src).group(1))
    assert seconds >= 10, "headcount refresh would burn the read quota"


def test_spreadsheet_handle_is_not_reopened_per_call(counting_book):
    """Re-opening the book costs a metadata fetch; tabs are cached on it."""
    book, counter = counting_book
    sl.open_meeting(now=T0)
    mid = sl.active_meeting()["meeting_id"]
    reads_after_setup = counter["reads"]

    for _ in range(5):
        sl.open_sessions(mid)

    # 5 reads of the log tab, and no repeated worksheet() metadata lookups
    assert counter["reads"] - reads_after_setup == 5


def test_rate_limited_calls_are_retried(monkeypatch):
    import gspread
    calls = {"n": 0}

    Resp = _fake_response(429)

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise gspread.exceptions.APIError(Resp())
        return "ok"

    monkeypatch.setattr(sl.time, "sleep", lambda s: None)
    assert sl._with_retry(flaky) == "ok"
    assert calls["n"] == 3


def test_non_rate_limit_errors_are_not_retried(monkeypatch):
    import gspread
    calls = {"n": 0}

    Resp = _fake_response(403)

    def denied():
        calls["n"] += 1
        raise gspread.exceptions.APIError(Resp())

    monkeypatch.setattr(sl.time, "sleep", lambda s: None)
    with pytest.raises(gspread.exceptions.APIError):
        sl._with_retry(denied)
    assert calls["n"] == 1, "a permission error must fail fast, not retry"


def test_student_page_shows_a_friendly_message_not_a_traceback(monkeypatch, fake_book):
    import gspread

    Resp = _fake_response(429)

    monkeypatch.setattr(sl, "active_meeting",
                        lambda: (_ for _ in ()).throw(gspread.exceptions.APIError(Resp())))
    at = _run("12_checkin.py")
    _no_exceptions(at)
    assert any("busy right now" in e.value for e in at.error)


# ── Hours page ──────────────────────────────────────────────────────────────

def test_hours_page_requires_login(fake_book):
    at = _run("14_hours.py")
    _no_exceptions(at)
    assert [t.label for t in at.text_input] == ["Username", "Password"]


def test_hours_page_empty_state(fake_book):
    at = _run("14_hours.py", admin_authed=True)
    _no_exceptions(at)
    assert any("no hours to show" in i.value for i in at.info)


def test_hours_page_shows_totals(fake_book):
    m = sl.open_meeting(now=T0)
    mid = m["meeting_id"]
    from datetime import timedelta
    sl.check_in(mid, "Eshan Nayak", now=T0)
    sl.check_out(mid, "Eshan Nayak", now=T0 + timedelta(minutes=90))
    sl.check_in(mid, "JD Queen", now=T0)
    sl.check_out(mid, "JD Queen", now=T0 + timedelta(minutes=30))

    at = _run("14_hours.py", admin_authed=True)
    _no_exceptions(at)
    metrics = {m_.label: m_.value for m_ in at.metric}
    assert metrics["Total hours"] == "2.00"
    assert metrics["Total minutes"] == "120"
    assert metrics["Sessions counted"] == "2"
    assert metrics["Members"] == "2"


def test_hours_page_flags_still_open_sessions(fake_book):
    m = sl.open_meeting(now=T0)
    sl.check_in(m["meeting_id"], "Eshan Nayak", now=T0)
    at = _run("14_hours.py", admin_authed=True)
    _no_exceptions(at)
    assert any("still open" in c.value for c in at.caption)
    assert {m_.label: m_.value for m_ in at.metric}["Total hours"] == "0.00"


def test_hours_page_filters_to_one_member(fake_book):
    from datetime import timedelta
    m = sl.open_meeting(now=T0)
    mid = m["meeting_id"]
    sl.check_in(mid, "Eshan Nayak", now=T0)
    sl.check_out(mid, "Eshan Nayak", now=T0 + timedelta(minutes=45))
    sl.check_in(mid, "JD Queen", now=T0)
    sl.check_out(mid, "JD Queen", now=T0 + timedelta(minutes=15))

    at = _run("14_hours.py", admin_authed=True)
    at.selectbox[0].set_value("Eshan Nayak").run()
    _no_exceptions(at)
    assert any("45 minutes (0.75 hours)" in c.value for c in at.caption)


# ── Load: the whole team arriving at once ──────────────────────────────────

def test_many_students_share_one_cached_read(counting_book, monkeypatch):
    """
    The failure in the field: a team scans the QR together and everyone's page
    reads the sheet independently. st.cache_data is shared across sessions, so
    N students must cost roughly one read, not N.
    """
    book, counter = counting_book
    sl.open_meeting(now=T0)
    mid = sl.active_meeting()["meeting_id"]
    sl.invalidate_cache()

    before = counter["reads"]
    for _ in range(40):                       # 40 students loading the page
        sl.sessions_for(mid, cached=True)
    after = counter["reads"]

    assert after - before <= 1, f"40 cached reads cost {after - before} API calls"


def test_uncached_reads_are_still_available_for_correctness(counting_book):
    book, counter = counting_book
    sl.open_meeting(now=T0)
    mid = sl.active_meeting()["meeting_id"]
    before = counter["reads"]
    for _ in range(3):
        sl.sessions_for(mid)                  # no cached= -> always fresh
    assert counter["reads"] - before == 3


def test_check_in_costs_no_read_when_given_the_frame(counting_book):
    """The hot path must be one write, not a read plus a write."""
    book, counter = counting_book
    sl.open_meeting(now=T0)
    mid = sl.active_meeting()["meeting_id"]
    sessions = sl.sessions_for(mid)

    before = counter["reads"]
    for i in range(20):
        sl.check_in(mid, f"Student {i}", now=T0, sessions=sessions)
    assert counter["reads"] == before, "check_in should not read when handed the frame"
    assert len(sl.sessions_for(mid)) == 20


def test_duplicate_appends_are_collapsed_on_read(fake_book):
    """
    A double-tap inside the cache window can append twice. Hours and headcounts
    must not double-count it.
    """
    m = sl.open_meeting(now=T0)
    mid = m["meeting_id"]
    stale = sl.sessions_for(mid)              # empty snapshot
    sl.check_in(mid, "Eshan Nayak", now=T0, sessions=stale)
    sl.check_in(mid, "Eshan Nayak", now=T0, sessions=stale)   # same stale view

    assert len(sl.sessions_for(mid)) == 1
    assert sl.open_sessions(mid) == ["Eshan Nayak"]
    assert len(sl.all_sessions()) == 1


def test_opening_a_meeting_takes_effect_immediately(counting_book):
    """A mentor starting the meeting must not wait for a cache to expire."""
    book, counter = counting_book
    assert sl.active_meeting(cached=True) is None
    sl.open_meeting(now=T0)
    assert sl.active_meeting(cached=True) is not None


def test_closing_a_meeting_takes_effect_immediately(counting_book):
    book, counter = counting_book
    m = sl.open_meeting(now=T0)
    assert sl.active_meeting(cached=True) is not None
    sl.close_meeting(m["meeting_id"], now=T0)
    assert sl.active_meeting(cached=True) is None


def test_student_sees_their_own_check_in_before_the_cache_refreshes(fake_book):
    m = sl.open_meeting(now=T0)
    mid = m["meeting_id"]
    at = _run("12_checkin.py")
    at.selectbox[0].set_value("Eshan Nayak").run()
    at.text_input[0].set_value(code("in", mid)).run()
    [b for b in at.button if b.label == "Check in"][0].click().run()
    _no_exceptions(at)

    # the shared cache is still stale, but their own page must show them as in
    at.selectbox[0].set_value("Eshan Nayak").run()
    assert any("You're checked in" in s.value for s in at.success)
    assert any(b.label == "Check out" for b in at.button)


# ── Write capacity ─────────────────────────────────────────────────────────

class WriteCountingWorksheet(conftest.FakeWorksheet):
    def __init__(self, *a, counter=None, **kw):
        super().__init__(*a, **kw)
        self.counter = counter if counter is not None else {"writes": 0}

    def append_row(self, values, value_input_option=None):
        self.counter["writes"] += 1
        super().append_row(values, value_input_option)

    def append_rows(self, values, value_input_option=None):
        self.counter["writes"] += 1          # one API call for the whole batch
        super().append_rows(values, value_input_option)

    def update_cell(self, row, col, value):
        self.counter["writes"] += 1
        super().update_cell(row, col, value)

    def batch_update(self, body, value_input_option=None):
        self.counter["writes"] += 1          # one API call for every cell
        for item in body:
            import re
            m = re.match(r"([A-Z]+)(\d+)", item["range"])
            col = 0
            for ch in m.group(1):
                col = col * 26 + (ord(ch) - 64)
            conftest.FakeWorksheet.update_cell(self, int(m.group(2)), col,
                                               item["values"][0][0])


class WriteCountingBook(conftest.FakeSpreadsheet):
    def __init__(self, counter):
        super().__init__("Fake", tabs={})
        self.counter = counter

    def add_worksheet(self, title, rows=100, cols=20):
        ws = WriteCountingWorksheet([], title=title, counter=self.counter)
        ws.spreadsheet = self
        self.tabs[title] = ws
        return ws


@pytest.fixture
def write_book(monkeypatch):
    counter = {"writes": 0}
    book = WriteCountingBook(counter)
    monkeypatch.setattr(sl, "_spreadsheet", lambda: book)
    return book, counter


def test_closing_a_big_meeting_is_one_batched_write(write_book):
    """
    Regression: closing a meeting wrote three cells per person still signed in
    — 228 writes for a team of 76, far past the 60/min quota, so ending the
    meeting failed outright.
    """
    book, counter = write_book
    m = sl.open_meeting(now=T0)
    mid = m["meeting_id"]
    sessions = sl.sessions_for(mid)
    for i in range(76):
        sl.check_in(mid, f"Student {i}", now=T0, sessions=sessions)

    before = counter["writes"]
    result = sl.close_meeting(mid, now=T0)
    spent = counter["writes"] - before

    assert len(result["auto_checked_out"]) == 76
    assert spent <= 4, f"closing a 76-person meeting cost {spent} writes"


def test_concurrent_check_ins_are_coalesced(write_book, monkeypatch):
    """
    Rows queued while another thread is flushing go out in that next flush, so
    a rush costs far fewer writes than it has students.
    """
    import threading
    book, counter = write_book
    m = sl.open_meeting(now=T0)
    mid = m["meeting_id"]
    sessions = sl.sessions_for(mid)

    real_append = WriteCountingWorksheet.append_rows
    gate = threading.Event()

    def slow_append(self, values, value_input_option=None):
        gate.wait(timeout=2)                 # hold the first flush open
        return real_append(self, values, value_input_option)

    monkeypatch.setattr(WriteCountingWorksheet, "append_rows", slow_append)

    before = counter["writes"]
    threads = [threading.Thread(target=sl.check_in,
                                args=(mid, f"Student {i}"),
                                kwargs={"now": T0, "sessions": sessions})
               for i in range(30)]
    for t in threads:
        t.start()
    gate.set()
    for t in threads:
        t.join(timeout=5)

    monkeypatch.setattr(WriteCountingWorksheet, "append_rows", real_append)
    sl.flush_pending()

    spent = counter["writes"] - before
    assert len(sl.sessions_for(mid)) == 30, "every student must still be recorded"
    assert spent < 30, f"30 concurrent check-ins cost {spent} writes, no coalescing"


def test_a_failed_flush_keeps_the_rows_queued(write_book, monkeypatch):
    """Nothing may be dropped if the sheet rejects the write."""
    book, counter = write_book
    m = sl.open_meeting(now=T0)
    mid = m["meeting_id"]

    def boom(self, values, value_input_option=None):
        raise RuntimeError("sheet unavailable")

    monkeypatch.setattr(WriteCountingWorksheet, "append_rows", boom)
    with pytest.raises(RuntimeError):
        sl.check_in(mid, "Eshan Nayak", now=T0, sessions=sl.sessions_for(mid))
    assert sl.pending_count() == 1

    monkeypatch.undo()
    sl.flush_pending()
    assert sl.pending_count() == 0
    assert sl.open_sessions(mid) == ["Eshan Nayak"]


def test_a_fresh_read_includes_queued_rows(write_book):
    book, counter = write_book
    m = sl.open_meeting(now=T0)
    mid = m["meeting_id"]
    sl.check_in(mid, "Eshan Nayak", now=T0, sessions=sl.sessions_for(mid))
    assert sl.pending_count() == 0          # flushed on the way out
    assert sl.open_sessions(mid) == ["Eshan Nayak"]
