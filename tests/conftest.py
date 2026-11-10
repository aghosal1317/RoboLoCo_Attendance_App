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
    """Mimics the slice of gspread.Spreadsheet the app uses, including tabs."""

    def __init__(self, title, tabs=None):
        self.title = title
        self.tabs = tabs if tabs is not None else {}

    def worksheet(self, name):
        import gspread
        if name not in self.tabs:
            raise gspread.WorksheetNotFound(name)
        return self.tabs[name]

    def add_worksheet(self, title, rows=100, cols=20):
        ws = FakeWorksheet([], title=title, spreadsheet_title=self.title)
        ws.spreadsheet = self
        self.tabs[title] = ws
        return ws

    def worksheets(self):
        return list(self.tabs.values())


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

    def append_row(self, values, value_input_option=None):
        self.rows.append([str(v) for v in values])

    def append_rows(self, values, value_input_option=None):
        for row in values:
            self.rows.append([str(v) for v in row])

    def batch_update(self, body, value_input_option=None):
        """Applies [{"range": "C7", "values": [[v]]}] like gspread does."""
        import re
        self.batch_updates = getattr(self, "batch_updates", 0) + 1
        for item in body:
            match = re.match(r"([A-Z]+)(\d+)", item["range"])
            letters, row = match.group(1), int(match.group(2))
            col = 0
            for ch in letters:
                col = col * 26 + (ord(ch) - 64)
            value = item["values"][0][0]
            self.update_cell(row, col, value)

    def update_cell(self, row, col, value):
        while len(self.rows) < row:
            self.rows.append([])
        target = self.rows[row - 1]
        while len(target) < col:
            target.append("")
        target[col - 1] = str(value)


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


@pytest.fixture
def fake_book(monkeypatch):
    """
    A fake spreadsheet for the check-in log: session_log creates its own tabs,
    so tests get the book rather than a single worksheet.
    """
    import session_log
    book = FakeSpreadsheet("Fake Attendance", tabs={})
    monkeypatch.setattr(session_log, "_spreadsheet", lambda: book)
    return book
