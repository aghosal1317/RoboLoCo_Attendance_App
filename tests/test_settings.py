import json

import settings


def test_parse_sheet_id_accepts_url_and_bare_id():
    url = "https://docs.google.com/spreadsheets/d/1bwqw-1DzP1netXcp_L7XLEWg3BZh5glSeshDY9jeprs/edit?usp=sharing"
    assert settings.parse_sheet_id(url) == "1bwqw-1DzP1netXcp_L7XLEWg3BZh5glSeshDY9jeprs"
    assert settings.parse_sheet_id("  1bwqw-1DzP1netXcp_L7XLEWg3BZh5glSeshDY9jeprs ") == \
        "1bwqw-1DzP1netXcp_L7XLEWg3BZh5glSeshDY9jeprs"


def test_parse_sheet_id_rejects_garbage():
    assert settings.parse_sheet_id("") is None
    assert settings.parse_sheet_id(None) is None
    assert settings.parse_sheet_id("not a sheet") is None
    assert settings.parse_sheet_id("https://example.com/foo") is None


def test_sheet_id_resolution_order(tmp_paths, monkeypatch):
    # No file, no secret -> default
    monkeypatch.setattr(settings, "get_secret", lambda k, d=None: d)
    assert settings.get_sheet_id() == settings.DEFAULT_SHEET_ID
    assert settings.get_sheet_id_source() == "default"

    # Secret set -> secret wins over default
    monkeypatch.setattr(settings, "get_secret", lambda k, d=None: "SECRETSHEETID_0123456789abc" if k == "SHEET_ID" else d)
    assert settings.get_sheet_id() == "SECRETSHEETID_0123456789abc"
    assert settings.get_sheet_id_source() == "secrets"

    # File set -> file wins over secret
    new_id = settings.set_sheet_id("https://docs.google.com/spreadsheets/d/FILESHEETID_0123456789abcdef/edit")
    assert new_id == "FILESHEETID_0123456789abcdef"
    assert settings.get_sheet_id() == "FILESHEETID_0123456789abcdef"
    assert settings.get_sheet_id_source() == "settings file"
    assert json.load(open(tmp_paths["settings"]))["sheet_id"] == "FILESHEETID_0123456789abcdef"

    # Clearing drops back to the secret
    settings.clear_sheet_id()
    assert settings.get_sheet_id() == "SECRETSHEETID_0123456789abc"


def test_set_sheet_id_rejects_invalid(tmp_paths):
    import pytest
    with pytest.raises(ValueError):
        settings.set_sheet_id("nope")
    assert not tmp_paths["settings"].exists()


def test_corrupt_settings_file_is_ignored(tmp_paths, no_secrets):
    tmp_paths["settings"].write_text("{not json")
    assert settings.get_sheet_id() == settings.DEFAULT_SHEET_ID


def test_admin_login_defaults(no_secrets):
    assert settings.check_admin_login("adrblc", "5338")
    assert settings.check_admin_login(" adrblc ", "5338")   # stray spaces in username ok
    assert not settings.check_admin_login("adrblc", "5339")
    assert not settings.check_admin_login("admin", "5338")
    assert not settings.check_admin_login("", "")
    assert not settings.check_admin_login(None, None)


def test_admin_login_overridable_via_secrets(monkeypatch):
    creds = {"admin_username": "coach", "admin_password": "s3cret"}
    monkeypatch.setattr(settings, "get_secret", lambda k, d=None: creds.get(k, d))
    assert settings.check_admin_login("coach", "s3cret")
    assert not settings.check_admin_login("adrblc", "5338")


def test_get_secret_swallows_missing_secrets_file(monkeypatch):
    class Boom:
        def get(self, *a, **k):
            raise RuntimeError("No secrets found")
    monkeypatch.setattr(settings.st, "secrets", Boom())
    assert settings.get_secret("SHEET_ID", "fallback") == "fallback"
