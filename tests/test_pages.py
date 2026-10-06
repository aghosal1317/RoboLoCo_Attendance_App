"""
End-to-end page tests with streamlit.testing.AppTest. Each test runs a real
page script, drives its widgets, and checks what reached the (fake) sheet.
"""
import json
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import conftest
import streamlit as st

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
    # pages cache roster reads; a cache surviving into the next test would serve
    # it the previous test's fake sheet
    st.cache_data.clear()
    yield
    st.cache_data.clear()


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
    at = _run("3_slack_sync.py", slack_results=results)
    _no_exceptions(at)
    at.date_input[0].set_value(TUESDAY).run()
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


# ── Slack Sync: messages that only invite some subteams ─────────────────────

from slack_integration import SUBTEAM_EMOJIS

ALL_SUBTEAMS = sorted(set(SUBTEAM_EMOJIS.values()))

SUBSET_RESULTS = {
    "Mechanical": ["Srin Dasari"], "Software": ["Julia Miller"],
    "Executive": ["Eshan Nayak"], "Loco": [],
    "wont_attend": ["JD Queen"],
    "invited": {"Mechanical", "Software", "Executive"},
    "text": "Mech, react :hammer_and_wrench:. Software react :computer:. Leadership, react :briefcase:.",
}


def test_slack_sync_partial_invite_does_not_mark_loco_absent(fake_ws):
    at = _run("3_slack_sync.py", slack_results=dict(SUBSET_RESULTS))
    at.date_input[0].set_value(TUESDAY).run()
    _no_exceptions(at)

    # the page tells the user Loco was left out, and pre-selects the other three
    assert any("Loco" in i.value for i in at.info)
    assert sorted(at.multiselect[0].value) == ["Executive", "Mechanical", "Software"]

    [b for b in at.button if b.label == "Save to Attendance Sheet"][0].click().run()
    _no_exceptions(at)

    header = fake_ws.rows[0]
    col = header.index("01/13/26")
    by_name = {r[header.index("Full Name")]: r[col] for r in fake_ws.rows[1:]}
    assert by_name["Eshan Nayak"] == "P"     # Executive, reacted
    assert by_name["Julia Miller"] == "P"    # Software, reacted
    assert by_name["Srin Dasari"] == "P"     # Mechanical, reacted
    assert by_name["JD Queen"] == "O"        # Loco, never invited


def test_slack_sync_user_can_override_uninvited_to_absent(fake_ws):
    at = _run("3_slack_sync.py", slack_results=dict(SUBSET_RESULTS))
    at.date_input[0].set_value(TUESDAY).run()
    at.radio[0].set_value("A").run()
    [b for b in at.button if b.label == "Save to Attendance Sheet"][0].click().run()
    _no_exceptions(at)

    header = fake_ws.rows[0]
    col = header.index("01/13/26")
    by_name = {r[header.index("Full Name")]: r[col] for r in fake_ws.rows[1:]}
    assert by_name["JD Queen"] == "A"


def test_slack_sync_user_can_add_a_subteam_the_message_missed(fake_ws):
    at = _run("3_slack_sync.py", slack_results=dict(SUBSET_RESULTS))
    at.date_input[0].set_value(TUESDAY).run()
    at.multiselect[0].set_value(ALL_SUBTEAMS).run()
    _no_exceptions(at)
    assert not at.radio   # nothing is uninvited any more, so no code picker
    [b for b in at.button if b.label == "Save to Attendance Sheet"][0].click().run()
    _no_exceptions(at)

    header = fake_ws.rows[0]
    col = header.index("01/13/26")
    by_name = {r[header.index("Full Name")]: r[col] for r in fake_ws.rows[1:]}
    assert by_name["JD Queen"] == "A"   # Loco now invited and silent


def test_slack_sync_full_team_message_marks_everyone(fake_ws):
    results = dict(SUBSET_RESULTS)
    results["invited"] = set(ALL_SUBTEAMS)
    at = _run("3_slack_sync.py", slack_results=results)
    at.date_input[0].set_value(TUESDAY).run()
    _no_exceptions(at)
    assert any("every subteam" in c.value for c in at.caption)
    assert not at.radio
    [b for b in at.button if b.label == "Save to Attendance Sheet"][0].click().run()

    header = fake_ws.rows[0]
    col = header.index("01/13/26")
    by_name = {r[header.index("Full Name")]: r[col] for r in fake_ws.rows[1:]}
    assert by_name["JD Queen"] == "A"


def test_slack_sync_blocks_save_with_no_subteams_selected(fake_ws):
    at = _run("3_slack_sync.py", slack_results=dict(SUBSET_RESULTS))
    at.date_input[0].set_value(TUESDAY).run()
    at.multiselect[0].set_value([]).run()
    _no_exceptions(at)
    assert any("at least one subteam" in w.value for w in at.warning)
    assert fake_ws.updates == []


def test_slack_sync_uses_the_date_picker_not_the_fetch_time_date(fake_ws):
    """Changing the date after fetching must change where attendance is written."""
    at = _run("3_slack_sync.py", slack_results=dict(SUBSET_RESULTS))
    at.date_input[0].set_value(TUESDAY).run()
    assert any("Saving to **01/13/26**" in c.value for c in at.caption)

    at.date_input[0].set_value(date(2026, 1, 15)).run()
    assert any("Saving to **01/15/26**" in c.value for c in at.caption)
    [b for b in at.button if b.label == "Save to Attendance Sheet"][0].click().run()
    _no_exceptions(at)

    header = fake_ws.rows[0]
    assert "01/15/26" in header
    col = header.index("01/15/26")
    by_name = {r[header.index("Full Name")]: r[col] for r in fake_ws.rows[1:]}
    assert by_name["Eshan Nayak"] == "P"
    # the fetch-time default date was never written
    assert all(r[header.index("01/13/26")] in ("P", "A", "L", "O", "Z", "") for r in fake_ws.rows[1:])
    assert any("Attendance saved for 01/15/26" in s.value for s in at.success)


def test_slack_sync_optional_toggle_applies_at_save_time(fake_ws):
    at = _run("3_slack_sync.py", slack_results=dict(SUBSET_RESULTS))
    at.date_input[0].set_value(TUESDAY)
    at.toggle[0].set_value(True).run()
    [b for b in at.button if b.label == "Save to Attendance Sheet"][0].click().run()
    _no_exceptions(at)

    header = fake_ws.rows[0]
    col = header.index("01/13/26")
    by_name = {r[header.index("Full Name")]: r[col] for r in fake_ws.rows[1:]}
    assert by_name["Srin Dasari"] == "P"   # reacted
    assert by_name["JD Queen"] == "O"      # Loco, uninvited


WORKSHOP_RESULTS = {
    "Mechanical": ["Srin Dasari"], "Software": ["Julia Miller"],
    "Executive": ["Eshan Nayak"], "Loco": ["JD Queen"], "Mentors": [],
    "Coaches": ["Coach Smith", "Coach Jones"],
    "wont_attend": [],
    "invited": {"Mechanical", "Software", "Loco", "Executive", "Mentors", "Coaches"},
    "text": "Build :hammer_and_wrench:. Programming :computer:. Loco :art:. "
            "Leadership :briefcase:. Mentors :memo:. Coaches :school:.",
}


def test_slack_sync_records_coaches_like_any_other_subteam(fake_ws):
    at = _run("3_slack_sync.py", slack_results=dict(WORKSHOP_RESULTS))
    at.date_input[0].set_value(TUESDAY).run()
    _no_exceptions(at)

    # Coaches are selectable and recorded
    assert "Coaches" in at.multiselect[0].options
    assert "Coaches" in at.multiselect[0].value

    [b for b in at.button if b.label == "Save to Attendance Sheet"][0].click().run()
    _no_exceptions(at)

    header = fake_ws.rows[0]
    col = header.index("01/13/26")
    by_name = {r[header.index("Full Name")]: r[col] for r in fake_ws.rows[1:]}
    assert by_name == {"Eshan Nayak": "P", "JD Queen": "P",
                       "Julia Miller": "P", "Srin Dasari": "P"}
    # the fake roster has no coach rows, so they're flagged as needing adding
    warnings = " ".join(w.value for w in at.warning)
    assert "coach smith" in warnings.lower()


def test_slack_sync_mentors_invited_with_no_reactions_is_not_treated_as_uninvited(fake_ws):
    at = _run("3_slack_sync.py", slack_results=dict(WORKSHOP_RESULTS))
    _no_exceptions(at)
    assert "Mentors" in at.multiselect[0].value          # pre-ticked from the text
    assert not at.radio                                   # nothing uninvited -> no code picker
    assert any("every subteam" in c.value for c in at.caption)


def test_slack_sync_labels_use_the_slack_wording(fake_ws):
    at = _run("3_slack_sync.py", slack_results=dict(WORKSHOP_RESULTS))
    labels = [m.label for m in at.metric]
    assert "Mechanical / Build" in labels
    assert "Software / Programming" in labels
    assert "Executive / Leadership" in labels


# ── Coaches on the Dashboard ────────────────────────────────────────────────

COACH_ROWS = [
    ["Last Name", "First Name", "Full Name", "% Meetings Attended", "01/13/26", "Subteam"],
    ["Nayak", "Eshan", "Eshan Nayak", "", "A", "Software"],
    ["Queen", "JD", "JD Queen", "", "A", "Loco"],
    ["Smith", "Coach", "Coach Smith", "", "P", "Coaches"],
]


def test_dashboard_excludes_coaches_from_team_stats(monkeypatch):
    ws = conftest.FakeWorksheet(COACH_ROWS)
    monkeypatch.setattr(dl, "_get_worksheet", lambda sheet_id=None: ws)
    at = _run("1_dashboard.py")
    _no_exceptions(at)

    metrics = {m.label: m.value for m in at.metric}
    # both members were absent; the coach's P must not lift the average off 0
    assert metrics["Overall Average"] == "0.0%"
    assert metrics["Members Below 70%"] == "2"      # the coach is not a third
    assert "100.0%" not in metrics["Attendance on 01/13/26"]


def test_dashboard_shows_coaches_in_their_own_panel(monkeypatch):
    ws = conftest.FakeWorksheet(COACH_ROWS)
    monkeypatch.setattr(dl, "_get_worksheet", lambda sheet_id=None: ws)
    at = _run("1_dashboard.py")
    _no_exceptions(at)
    assert any("Coaches (1)" in e.label and "not held to 70%" in e.label for e in at.expander)


def test_dashboard_has_no_coach_panel_when_sheet_has_none(fake_ws):
    at = _run("1_dashboard.py")
    _no_exceptions(at)
    assert not any("Coaches" in e.label for e in at.expander)


# ── The double-checker ──────────────────────────────────────────────────────

def _dated(text):
    r = dict(SUBSET_RESULTS)
    r["text"] = text
    return r


def test_double_check_flags_a_date_mismatch(fake_ws):
    at = _run("3_slack_sync.py", slack_results=_dated("Attendance for Thursday's meeting, 7/23."))
    at.date_input[0].set_value(TUESDAY).run()          # 01/13/26, not 7/23
    _no_exceptions(at)
    errors = " ".join(e.value for e in at.error)
    assert "Date mismatch" in errors
    assert "07/23/26" in errors and "01/13/26" in errors
    # dates only -- no weekday names in the message
    assert "Thursday" not in errors and "Tuesday" not in errors


def test_double_check_button_adopts_the_message_date(fake_ws):
    at = _run("3_slack_sync.py", slack_results=_dated("Attendance for Thursday's meeting, 7/23."))
    at.date_input[0].set_value(TUESDAY).run()
    [b for b in at.button if "Use the message" in b.label][0].click().run()
    _no_exceptions(at)

    assert at.date_input[0].value == date(2026, 7, 23)
    assert any("Date matches" in s.value for s in at.success)
    assert not any("Date mismatch" in e.value for e in at.error)

    [b for b in at.button if b.label == "Save to Attendance Sheet"][0].click().run()
    _no_exceptions(at)
    assert "07/23/26" in fake_ws.rows[0]


def test_double_check_confirms_a_matching_date(fake_ws):
    at = _run("3_slack_sync.py", slack_results=_dated("Meeting on 01/13/26 everyone"))
    at.date_input[0].set_value(TUESDAY).run()
    _no_exceptions(at)
    assert any("Date matches" in s.value for s in at.success)


def test_double_check_warns_before_overwriting_a_recorded_date(fake_ws):
    at = _run("3_slack_sync.py", slack_results=_dated("Meeting on 01/13/26"))
    at.date_input[0].set_value(TUESDAY).run()
    _no_exceptions(at)
    warnings = " ".join(w.value for w in at.warning)
    assert "already has 3 entries" in warnings
    assert "Saving replaces" in warnings


def test_double_check_lists_reactors_missing_from_the_roster(fake_ws):
    results = _dated("Meeting on 01/15/26")
    results["Mechanical"] = ["Srin Dasari", "Totally New Person"]
    at = _run("3_slack_sync.py", slack_results=results)
    at.date_input[0].set_value(date(2026, 1, 15)).run()
    _no_exceptions(at)
    warnings = " ".join(w.value for w in at.warning)
    assert "aren't on the roster" in warnings
    assert "Totally New Person" in warnings


def test_double_check_says_nothing_is_wrong_when_all_clear(fake_ws):
    at = _run("3_slack_sync.py", slack_results=_dated("Meeting on 01/15/26"))
    at.date_input[0].set_value(date(2026, 1, 15)).run()   # unused date, all names known
    _no_exceptions(at)
    assert any("Everything lines up" in c.value for c in at.caption)


def test_double_check_handles_a_message_with_no_date(fake_ws):
    at = _run("3_slack_sync.py", slack_results=_dated("Practice tonight, react if coming"))
    _no_exceptions(at)
    assert any("No date found in the message" in c.value for c in at.caption)


def test_date_mismatch_blocks_saving_until_acknowledged(fake_ws):
    at = _run("3_slack_sync.py", slack_results=_dated("Attendance for Thursday's meeting, 7/23."))
    at.date_input[0].set_value(TUESDAY).run()
    _no_exceptions(at)

    save = [b for b in at.button if b.label == "Save to Attendance Sheet"][0]
    assert save.disabled
    confirm = [c for c in at.checkbox if "dates differ" in c.label][0]

    confirm.check().run()
    save = [b for b in at.button if b.label == "Save to Attendance Sheet"][0]
    assert not save.disabled
    save.click().run()
    _no_exceptions(at)
    assert any("Attendance saved for 01/13/26" in s.value for s in at.success)


def test_no_acknowledgement_needed_when_dates_agree(fake_ws):
    at = _run("3_slack_sync.py", slack_results=_dated("Meeting on 01/13/26"))
    at.date_input[0].set_value(TUESDAY).run()
    _no_exceptions(at)
    assert not any("dates differ" in c.label for c in at.checkbox)
    assert not [b for b in at.button if b.label == "Save to Attendance Sheet"][0].disabled


def test_unknown_reactor_message_is_singular_for_one_person(fake_ws):
    results = _dated("Meeting on 01/15/26")
    results["Mechanical"] = ["Srin Dasari", "Totally New Person"]
    at = _run("3_slack_sync.py", slack_results=results)
    at.date_input[0].set_value(date(2026, 1, 15)).run()
    warnings = " ".join(w.value for w in at.warning)
    assert "1 person reacted" in warnings and "1 people" not in warnings
