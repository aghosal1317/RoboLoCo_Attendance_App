"""
End-to-end page tests with streamlit.testing.AppTest. Each test runs a real
page script, drives its widgets, and checks what reached the (fake) sheet.
"""
import json
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import data_loader as dl
import settings

TUESDAY = date(2026, 1, 13)
SATURDAY = date(2026, 1, 17)


def _run(page, **kw):
    at = AppTest.from_file(f"pages/{page}", default_timeout=30)
    for k, v in kw.items():
        at.session_state[k] = v
    return at.run()


def _no_exceptions(at):
    assert not at.exception, [e.value for e in at.exception]


@pytest.fixture(autouse=True)
def _isolate(fake_ws, tmp_paths, monkeypatch):
    monkeypatch.setattr(dl, "get_service_account_email", lambda: "bot@example.iam.gserviceaccount.com")
    yield


# ── Read-only pages just need to render ─────────────────────────────────────

@pytest.mark.parametrize("page", [
    "1_dashboard.py", "4_member_insights.py", "6_edit_specific_date.py",
    "7_google_drive_sync.py", "8_generate_qr.py", "10_settings.py",
])
def test_page_renders_without_error(page):
    _no_exceptions(_run(page))


def test_home_lists_settings_card():
    at = AppTest.from_file("home.py").run()
    _no_exceptions(at)
    assert any("Settings" in m.value for m in at.markdown)


def test_predictions_page_handles_small_dataset():
    at = _run("5_predictions.py")
    _no_exceptions(at)   # "not enough data" path must st.stop(), not crash


# ── Take Attendance ─────────────────────────────────────────────────────────

def test_take_attendance_selection_survives_search_and_marks_everyone(fake_ws):
    at = _run("2_take_attendance.py")
    _no_exceptions(at)
    at.date_input[0].set_value(TUESDAY).run()

    at.checkbox(key="att_Eshan Nayak").check().run()
    # Filter down to one other member: Eshan's checkbox is now unmounted
    at.text_input[0].set_value("queen").run()
    assert [c.label for c in at.checkbox] == ["JD Queen"]
    at.checkbox(key="att_JD Queen").check().run()
    assert "2** of 4 members marked present" in " ".join(c.value for c in at.caption)

    [b for b in at.button if b.label == "Submit Attendance"][0].click().run()
    _no_exceptions(at)

    assert any("Attendance saved for 01/13/26" in s.value for s in at.success)
    header = fake_ws.rows[0]
    col = header.index("01/13/26")
    by_name = {r[header.index("Full Name")]: r[col] for r in fake_ws.rows[1:]}
    assert by_name == {"Eshan Nayak": "P", "JD Queen": "P", "Julia Miller": "A", "Srin Dasari": "A"}
    # selections cleared after a successful save
    assert at.session_state["manual_checked"] == set()


def test_take_attendance_optional_saturday_writes_o_to_both_columns(fake_ws):
    at = _run("2_take_attendance.py")
    at.date_input[0].set_value(SATURDAY)
    at.toggle[0].set_value(True).run()
    assert any("Saturday" in c.value for c in at.caption)

    at.checkbox(key="att_Srin Dasari").check().run()
    [b for b in at.button if b.label == "Submit Attendance"][0].click().run()
    _no_exceptions(at)

    header = fake_ws.rows[0]
    assert "01/17/26" in header and "01/17/26.1" in header
    for col_name in ("01/17/26", "01/17/26.1"):
        col = header.index(col_name)
        assert [r[col] for r in fake_ws.rows[1:]] == ["O", "O", "O", "P"]


def test_take_attendance_does_not_push_when_loaded_from_csv(fake_ws, tmp_paths, monkeypatch):
    import pandas as pd
    pd.DataFrame({"Last Name": ["Nayak"], "First Name": ["Eshan"], "Subteam": ["Loco"]}).to_csv(
        tmp_paths["csv"], index=False)
    def boom(sheet_id=None):
        raise ConnectionError("offline")
    monkeypatch.setattr(dl, "_get_worksheet", boom)

    at = _run("2_take_attendance.py")
    _no_exceptions(at)
    assert any("Couldn't reach the Google Sheet" in w.value for w in at.warning)
    at.checkbox(key="att_Eshan Nayak").check().run()
    [b for b in at.button if b.label == "Submit Attendance"][0].click().run()
    _no_exceptions(at)
    assert any("NOT pushed" in e.value for e in at.error)
    assert fake_ws.updates == []


# ── Slack Sync ──────────────────────────────────────────────────────────────

def test_slack_sync_save(fake_ws):
    results = {"Mechanical": ["Srin Dasari"], "Software": ["julia miller"], "Loco": [],
               "Executive": ["Ghost Person"], "wont_attend": ["JD Queen"]}
    at = _run("3_slack_sync.py", slack_results=results, slack_date_str="01/13/26", slack_is_optional=False)
    _no_exceptions(at)
    [b for b in at.button if b.label == "Save to Attendance Sheet"][0].click().run()
    _no_exceptions(at)

    assert any("2 members marked present" in s.value for s in at.success)
    assert any("Ghost Person" in w.value.lower() or "ghost person" in w.value for w in at.warning)
    header = fake_ws.rows[0]
    col = header.index("01/13/26")
    by_name = {r[header.index("Full Name")]: r[col] for r in fake_ws.rows[1:]}
    assert by_name == {"Eshan Nayak": "A", "JD Queen": "A", "Julia Miller": "P", "Srin Dasari": "P"}
    assert "slack_results" not in at.session_state


def test_slack_sync_requires_token(monkeypatch):
    monkeypatch.setattr(settings, "get_secret", lambda k, d=None: d)
    at = _run("3_slack_sync.py")
    at.text_input[0].set_value("https://x.slack.com/archives/C1/p1700000000000000")
    [b for b in at.button if b.label == "Fetch Attendance"][0].click().run()
    assert any("SLACK_TOKEN" in e.value for e in at.error)


# ── QR Check-In ─────────────────────────────────────────────────────────────

def test_qr_checkin_submit(fake_ws):
    at = _run("9_qr_checkin.py", checked_in={"Eshan Nayak", "Unknown Scan"})
    _no_exceptions(at)
    at.date_input[0].set_value(TUESDAY).run()
    [b for b in at.button if b.label == "Submit Attendance"][0].click().run()
    _no_exceptions(at)

    assert any("1 present" in s.value for s in at.success)
    assert any("Unknown Scan" in w.value.lower() or "unknown scan" in w.value for w in at.warning)
    header = fake_ws.rows[0]
    col = header.index("01/13/26")
    assert [r[col] for r in fake_ws.rows[1:]] == ["P", "A", "A", "A"]
    assert at.session_state["checked_in"] == set()


def test_qr_checkin_refuses_empty_submit(fake_ws):
    at = _run("9_qr_checkin.py")
    [b for b in at.button if b.label == "Submit Attendance"][0].click().run()
    assert any("No one has checked in" in w.value for w in at.warning)
    assert fake_ws.updates == []


# ── Settings page ───────────────────────────────────────────────────────────

def test_settings_shows_instructions_and_service_account_before_login():
    at = _run("10_settings.py")
    _no_exceptions(at)
    assert any("from scratch" in h.value for h in at.subheader)
    body = " ".join(m.value for m in at.markdown)
    assert "Share" in body and "SHEET_ID" in body
    assert any("bot@example.iam.gserviceaccount.com" in c.value for c in at.code)
    # login form present, admin controls hidden
    assert [t.label for t in at.text_input] == ["Username", "Password"]
    assert not any(b.label == "Switch to this sheet" for b in at.button)


def test_settings_rejects_bad_login(tmp_paths):
    at = _run("10_settings.py")
    at.text_input[0].set_value("adrblc")
    at.text_input[1].set_value("wrong")
    at.button[0].click().run()
    assert any("Incorrect" in e.value for e in at.error)
    assert "admin_authed" not in at.session_state


def test_settings_login_test_and_switch(tmp_paths, monkeypatch):
    at = _run("10_settings.py")
    at.text_input[0].set_value("adrblc")
    at.text_input[1].set_value("5338")
    at.button[0].click().run()
    _no_exceptions(at)
    assert at.session_state["admin_authed"] is True

    new_url = "https://docs.google.com/spreadsheets/d/NEWSEASON_0123456789abcdefghij/edit#gid=0"
    url_box = [t for t in at.text_input if t.label.startswith("New spreadsheet")][0]
    url_box.set_value(new_url).run()

    [b for b in at.button if b.label == "Test connection"][0].click().run()
    _no_exceptions(at)
    assert any("Connected to" in s.value for s in at.success)
    assert [m.value for m in at.metric if m.label == "Members"] == ["4"]

    [b for b in at.button if b.label == "Switch to this sheet"][0].click().run()
    _no_exceptions(at)
    assert json.load(open(tmp_paths["settings"]))["sheet_id"] == "NEWSEASON_0123456789abcdefghij"
    assert settings.get_sheet_id() == "NEWSEASON_0123456789abcdefghij"
    assert any('SHEET_ID = "NEWSEASON_0123456789abcdefghij"' in c.value for c in at.code)


def test_settings_test_connection_reports_failure(tmp_paths, monkeypatch):
    def boom(sheet_id=None):
        raise PermissionError("403 The caller does not have permission")
    monkeypatch.setattr(dl, "_get_worksheet", boom)
    at = _run("10_settings.py", admin_authed=True)
    url_box = [t for t in at.text_input if t.label.startswith("New spreadsheet")][0]
    url_box.set_value("NEWSEASON_0123456789abcdefghij").run()
    [b for b in at.button if b.label == "Test connection"][0].click().run()
    assert any("Couldn't read that sheet" in e.value for e in at.error)
    assert not tmp_paths["settings"].exists()
