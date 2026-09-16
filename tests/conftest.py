"""
Shared fixtures. Nothing here touches the network: the Google Sheet is
replaced by an in-memory FakeWorksheet, and settings are written to a temp file.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import data_loader  # noqa: E402
import settings  # noqa: E402


class FakeSpreadsheet:
    def __init__(self, title):
        self.title = title


class FakeWorksheet:
    """Mimics the tiny slice of gspread.Worksheet the app uses."""

    def __init__(self, rows, title="Sheet1", spreadsheet_title="Fake Attendance"):
        self.rows = [list(r) for r in rows]
        self.title = title
        self.spreadsheet = FakeSpreadsheet(spreadsheet_title)
        self.cleared = 0
        self.updates = []

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def clear(self):
        self.cleared += 1
        self.rows = []

    def update(self, data):
        self.updates.append([list(r) for r in data])
        self.rows = [list(r) for r in data]


# Header + members in the app-written ("format B") layout, mirroring the live sheet.
# 01/10/26 is a Saturday (double session), 01/13/26 is a Tuesday.
FORMAT_B_ROWS = [
    ["Last Name", "First Name", "Full Name", "% Meetings Attended",
     "01/13/26", "01/10/26", "01/10/26.1", "01/08/26", "Subteam"],
    ["Nayak", "Eshan", "Eshan Nayak", "100", "P", "P", "P", "P", "Executive"],
    ["Queen", "JD", "JD Queen", "50", "A", "L", "P", "A", "Loco"],
    ["Miller", "Julia", "Julia Miller", "0", "O", "Z", "Z", "", "Software"],
    ["Dasari", "Srin", "Srin Dasari", "0", "", "", "", "", "Mechanical"],
]

# Hand-made ("format A") layout with subteam section rows and a Coaches block.
FORMAT_A_ROWS = [
    ["Last Name", "First Name", "% Meetings Attended", "01/08/26", "01/10/26", "01/10/26"],
    ["Executive", "", "", "", "", ""],
    ["Nayak", "Eshan", "100%", "P", "P", "P"],
    ["", "1", "", "", "", ""],          # count row
    ["Loco", "", "", "", "", ""],
    ["Queen", "JD", "50%", "A", "P", "L"],
    ["", "", "", "", "", ""],           # blank row
    ["Coaches", "", "", "", "", ""],
    ["Smith", "Coach", "", "P", "P", "P"],
]


@pytest.fixture
def fake_ws(monkeypatch):
    """Install a FakeWorksheet as the app's Google Sheet and return it."""
    ws = FakeWorksheet(FORMAT_B_ROWS)
    monkeypatch.setattr(data_loader, "_get_worksheet", lambda sheet_id=None: ws)
    return ws


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    """Redirect the CSV backup and settings file into a temp dir."""
    csv_path = tmp_path / "attendance.csv"
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(data_loader, "CSV_PATH", str(csv_path))
    monkeypatch.setattr(settings, "SETTINGS_PATH", str(settings_path))
    # get_sheet_id/set_sheet_id use the module constant as a default arg, so
    # re-bind their defaults too.
    for fn in ("get_sheet_id", "get_sheet_id_source", "set_sheet_id", "clear_sheet_id"):
        f = getattr(settings, fn)
        f.__defaults__ = (str(settings_path),)
    return {"csv": csv_path, "settings": settings_path}


@pytest.fixture
def no_secrets(monkeypatch):
    """Pretend no secrets file exists at all."""
    monkeypatch.setattr(settings, "get_secret", lambda key, default=None: default)


@pytest.fixture(autouse=True)
def _protect_real_backup():
    """Fail loudly if any test writes to the real data/attendance.csv."""
    real = os.path.join(ROOT, "data", "attendance.csv")
    before = os.stat(real).st_mtime_ns if os.path.exists(real) else None
    yield
    after = os.stat(real).st_mtime_ns if os.path.exists(real) else None
    assert before == after, "a test modified the real data/attendance.csv — redirect CSV_PATH via tmp_paths"
