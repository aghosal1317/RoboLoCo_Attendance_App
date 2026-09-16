import pandas as pd
import pytest

import data_loader as dl
from conftest import FakeWorksheet, FORMAT_A_ROWS, FORMAT_B_ROWS


# ── Parsing ─────────────────────────────────────────────────────────────────

def test_deduplicate_columns_matches_pandas_convention():
    assert dl._deduplicate_columns(["a", "b", "a", "a", "b"]) == ["a", "b", "a.1", "a.2", "b.1"]


def test_rows_to_frame_pads_short_rows():
    df = dl._rows_to_frame([["Last Name", "First Name", "Subteam"], ["Nayak", "Eshan"]])
    assert df.iloc[0].tolist() == ["Nayak", "Eshan", ""]


def test_rows_to_frame_rejects_empty():
    with pytest.raises(ValueError):
        dl._rows_to_frame([])


def test_load_format_b_sheet(fake_ws):
    df = dl.load_data()
    assert df.attrs["source"] == "sheet"
    assert df["Full Name"].tolist() == ["Eshan Nayak", "JD Queen", "Julia Miller", "Srin Dasari"]
    assert df["Subteam"].tolist() == ["Executive", "Loco", "Software", "Mechanical"]
    assert df["% Meetings Attended"].tolist() == [100.0, 50.0, 0.0, 0.0]
    # blanks are "" not NaN
    assert (df["01/08/26"] == ["P", "A", "", ""]).all()


def test_load_format_a_sheet_strips_headers_counts_blanks_and_coaches(monkeypatch):
    ws = FakeWorksheet(FORMAT_A_ROWS)
    monkeypatch.setattr(dl, "_get_worksheet", lambda sheet_id=None: ws)
    df = dl.load_data()
    assert df["Full Name"].tolist() == ["Eshan Nayak", "JD Queen"]
    assert df["Subteam"].tolist() == ["Executive", "Loco"]
    assert df["% Meetings Attended"].tolist() == [100.0, 50.0]
    # duplicate date headers become .1 columns
    assert dl.get_date_columns(df) == ["01/08/26", "01/10/26", "01/10/26.1"]
    assert df.loc[1, ["01/10/26", "01/10/26.1"]].tolist() == ["P", "L"]


def test_first_two_columns_are_renamed_by_position(monkeypatch):
    ws = FakeWorksheet([["Surname", "Given", "Subteam"], ["Nayak", "Eshan", "Loco"]])
    monkeypatch.setattr(dl, "_get_worksheet", lambda sheet_id=None: ws)
    df = dl.load_data()
    assert df["Full Name"].tolist() == ["Eshan Nayak"]


def test_csv_fallback_when_sheet_unreachable(monkeypatch, tmp_paths):
    pd.DataFrame({
        "Last Name": ["Nayak", None], "First Name": ["Eshan", None],
        "01/08/26": ["P", None], "Subteam": ["Loco", None],
    }).to_csv(tmp_paths["csv"], index=False)

    def boom(sheet_id=None):
        raise ConnectionError("no network")
    monkeypatch.setattr(dl, "_get_worksheet", boom)
    warnings = []
    monkeypatch.setattr(dl.st, "warning", lambda msg: warnings.append(msg))

    df = dl.load_data()
    assert df.attrs["source"] == "csv"
    assert df["Full Name"].tolist() == ["Eshan Nayak"]   # NaN row dropped, not kept as "nan nan"
    assert df["01/08/26"].tolist() == ["P"]
    assert warnings and "Couldn't reach the Google Sheet" in warnings[0]


# ── Date columns ────────────────────────────────────────────────────────────

def test_get_date_columns_sorted_chronologically_with_sessions_in_order():
    df = pd.DataFrame(columns=["Last Name", "02/07/26.1", "Full Name", "01/13/26",
                               "02/07/26", "12/04/25", "Subteam", "% Meetings Attended", "02/07/26.2"])
    assert dl.get_date_columns(df) == ["12/04/25", "01/13/26", "02/07/26", "02/07/26.1", "02/07/26.2"]


def test_get_date_columns_ignores_lookalikes():
    df = pd.DataFrame(columns=["01/13/26", "01/13/2026", "1/3/26", "01/13/26x", "Date"])
    assert dl.get_date_columns(df) == ["01/13/26"]


def test_is_saturday():
    assert dl.is_saturday("01/10/26")        # Saturday
    assert not dl.is_saturday("01/13/26")    # Tuesday
    assert dl.is_saturday("02/07/26")


def test_get_columns_for_date_creates_single_or_double():
    df = pd.DataFrame({"Full Name": ["A"]})
    assert dl.get_columns_for_date(df, "01/13/26") == ["01/13/26"]
    assert dl.get_columns_for_date(df, "01/10/26") == ["01/10/26", "01/10/26.1"]
    assert df["01/10/26.1"].tolist() == [""]
    # idempotent: existing columns aren't wiped
    df["01/10/26"] = ["P"]
    dl.get_columns_for_date(df, "01/10/26")
    assert df["01/10/26"].tolist() == ["P"]


# ── Melt / percentages ──────────────────────────────────────────────────────

def test_melt_attendance_codes(fake_ws):
    m = dl.melt_attendance(dl.load_data())
    jd = m[m["First Name"] == "JD"].set_index("Date")
    # both Saturday sessions collapse to the same date and both count
    sat = jd.loc[pd.Timestamp("2026-01-10")]
    assert sat["Present"].tolist() == [1, 1]           # L and P
    julia = m[m["First Name"] == "Julia"]
    assert julia["Counted"].sum() == 2                  # Z, Z counted; O and blank not
    assert julia["Present"].sum() == 0


def test_recalc_percentages_rules():
    df = pd.DataFrame({
        "Full Name": ["p", "mixed", "optional-only", "none"],
        "01/08/26": ["P", "P", "O", ""],
        "01/10/26": ["L", "A", "O", ""],
        "01/10/26.1": ["P", "Z", "", ""],
        "Subteam": ["x"] * 4,
    })
    out = dl.recalc_percentages(df)
    assert out["% Meetings Attended"].tolist() == [100.0, pytest.approx(33.33), 0.0, 0.0]


def test_recalc_percentages_no_dates():
    df = pd.DataFrame({"Full Name": ["a"]})
    assert dl.recalc_percentages(df)["% Meetings Attended"].tolist() == [0.0]


def test_recalc_percentages_handles_nan_and_whitespace():
    df = pd.DataFrame({"01/08/26": [" P ", None], "01/13/26": ["A", "A"]})
    assert dl.recalc_percentages(df)["% Meetings Attended"].tolist() == [50.0, 0.0]


# ── write_attendance: the shared path for Take Attendance / Slack / QR ──────

def test_write_attendance_regular_weekday(fake_ws):
    df = dl.load_data()
    matched, unknown = dl.write_attendance(df, "01/15/26", ["Eshan Nayak", "jd queen"], "A")
    assert matched == 2 and unknown == []
    assert df["01/15/26"].tolist() == ["P", "P", "A", "A"]
    assert "01/15/26.1" not in df.columns


def test_write_attendance_saturday_writes_both_sessions(fake_ws):
    df = dl.load_data()
    dl.write_attendance(df, "01/17/26", {"Julia Miller"}, "O")
    assert df["01/17/26"].tolist() == ["O", "O", "P", "O"]
    assert df["01/17/26.1"].tolist() == ["O", "O", "P", "O"]


def test_write_attendance_reports_unrecognized_and_overwrites(fake_ws):
    df = dl.load_data()
    matched, unknown = dl.write_attendance(df, "01/13/26", ["Eshan Nayak", "Nobody Here"], "A")
    assert matched == 1
    assert unknown == ["nobody here"]
    # existing column fully overwritten, every member has a status
    assert df["01/13/26"].tolist() == ["P", "A", "A", "A"]


# ── save_data round trip ────────────────────────────────────────────────────

def test_save_data_round_trip_orders_columns_and_pushes(fake_ws, tmp_paths):
    df = dl.load_data()
    dl.write_attendance(df, "01/06/26", ["Srin Dasari"], "A")   # backdated: created last
    df = dl.recalc_percentages(df)
    assert dl.save_data(df) is True

    assert fake_ws.cleared == 1
    header = fake_ws.rows[0]
    assert header == ["Last Name", "First Name", "Full Name", "% Meetings Attended",
                      "01/06/26", "01/08/26", "01/10/26", "01/10/26.1", "01/13/26", "Subteam"]
    # what we pushed reloads identically
    reloaded = dl.load_data()
    assert reloaded["Full Name"].tolist() == df["Full Name"].tolist()
    assert reloaded["01/06/26"].tolist() == ["A", "A", "A", "P"]
    assert reloaded["% Meetings Attended"].tolist() == df["% Meetings Attended"].tolist()
    # local backup written too
    assert pd.read_csv(tmp_paths["csv"]).shape[0] == 4


def test_save_data_never_pushes_csv_fallback_over_sheet(monkeypatch, fake_ws, tmp_paths):
    df = dl.load_data()
    df.attrs["source"] = "csv"
    errors = []
    monkeypatch.setattr(dl.st, "error", lambda m: errors.append(m))
    assert dl.save_data(df) is False
    assert fake_ws.cleared == 0 and fake_ws.updates == []
    assert errors and "NOT pushed" in errors[0]
    assert tmp_paths["csv"].exists()


def test_save_data_warns_when_push_fails(monkeypatch, fake_ws, tmp_paths):
    df = dl.load_data()
    def boom(sheet_id=None):
        raise RuntimeError("quota")
    monkeypatch.setattr(dl, "_get_worksheet", boom)
    warnings = []
    monkeypatch.setattr(dl.st, "warning", lambda m: warnings.append(m))
    assert dl.save_data(df) is False
    assert warnings and "could not sync" in warnings[0]


# ── inspect_sheet (Settings page "Test connection") ─────────────────────────

def test_inspect_sheet_format_b(fake_ws):
    r = dl.inspect_sheet("anything")
    assert r["title"] == "Fake Attendance"
    assert r["members"] == 4
    assert r["date_columns"] == 4
    assert r["layout"].startswith("Subteam column")
    assert r["subteams"] == {"Executive": 1, "Loco": 1, "Software": 1, "Mechanical": 1}
    assert r["warnings"] == []


def test_inspect_sheet_flags_problems(monkeypatch):
    ws = FakeWorksheet([
        ["Last Name", "First Name", "Email"],
        ["Nayak", "Eshan", "x"],
        ["Nayak", "Eshan", "y"],
        ["Queen", "JD", ""],
    ])
    monkeypatch.setattr(dl, "_get_worksheet", lambda sheet_id=None: ws)
    r = dl.inspect_sheet("id")
    joined = " ".join(r["warnings"])
    assert "no subteam" in joined
    assert "Duplicate names: Eshan Nayak" in joined
    assert "Ignored columns" in joined and "Email" in joined


def test_inspect_sheet_format_a(monkeypatch):
    ws = FakeWorksheet(FORMAT_A_ROWS)
    monkeypatch.setattr(dl, "_get_worksheet", lambda sheet_id=None: ws)
    r = dl.inspect_sheet("id")
    assert r["layout"].startswith("section headers")
    assert r["members"] == 2


def test_get_worksheet_uses_configured_sheet_id(monkeypatch):
    opened = []
    class Client:
        def open_by_key(self, key):
            opened.append(key)
            class S:
                sheet1 = "WS"
            return S()
    monkeypatch.setattr(dl, "_get_credentials", lambda: None)
    monkeypatch.setattr(dl.gspread, "authorize", lambda creds: Client())
    monkeypatch.setattr(dl, "get_sheet_id", lambda: "CONFIGURED")
    assert dl._get_worksheet() == "WS"
    assert dl._get_worksheet("EXPLICIT") == "WS"
    assert opened == ["CONFIGURED", "EXPLICIT"]
