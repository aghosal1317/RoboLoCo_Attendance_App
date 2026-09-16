"""
App-level settings that can change from season to season.

The one thing that changes every year is *which Google Sheet* holds the
roster and attendance. It is resolved in this order:

    1. data/settings.json          — written by the Settings page (admin login)
    2. st.secrets["SHEET_ID"]      — Streamlit Cloud "Secrets" (survives reboots)
    3. DEFAULT_SHEET_ID            — hardcoded fallback

On Streamlit Cloud the filesystem is wiped on every reboot / redeploy, so a
change made on the Settings page lasts until the next reboot. Putting the same
ID in Secrets makes it permanent. data/settings.json is git-ignored on purpose
so a stale committed copy can never override the secret.
"""
import hmac
import json
import os
import re

import streamlit as st

SETTINGS_PATH = "data/settings.json"
DEFAULT_SHEET_ID = "1bwqw-1DzP1netXcp_L7XLEWg3BZh5glSeshDY9jeprs"

# Admin login for the Settings page. Override in secrets.toml with
# admin_username / admin_password if you ever want to rotate them.
DEFAULT_ADMIN_USERNAME = "adrblc"
DEFAULT_ADMIN_PASSWORD = "5338"

_SHEET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")
_SHEET_URL_RE = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")


def get_secret(key, default=None):
    """st.secrets raises if no secrets file exists at all; treat that as 'unset'."""
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


def _read_settings_file(path=SETTINGS_PATH):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_settings_file(data, path=SETTINGS_PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def parse_sheet_id(text):
    """
    Accept either a full Google Sheets URL or a bare spreadsheet ID and
    return the ID. Returns None if the input doesn't look like either.
    """
    text = (text or "").strip()
    m = _SHEET_URL_RE.search(text)
    if m:
        return m.group(1)
    if _SHEET_ID_RE.match(text):
        return text
    return None


def sheet_url(sheet_id):
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"


def get_sheet_id(path=SETTINGS_PATH):
    """The spreadsheet ID the app should read from and write to right now."""
    file_id = _read_settings_file(path).get("sheet_id")
    if file_id:
        return file_id
    secret_id = get_secret("SHEET_ID")
    if secret_id:
        return str(secret_id).strip()
    return DEFAULT_SHEET_ID


def get_sheet_id_source(path=SETTINGS_PATH):
    """Where the active sheet ID came from — for display on the Settings page."""
    if _read_settings_file(path).get("sheet_id"):
        return "settings file"
    if get_secret("SHEET_ID"):
        return "secrets"
    return "default"


def set_sheet_id(sheet_id, path=SETTINGS_PATH):
    """Persist a new sheet ID. Raises ValueError on a malformed ID."""
    parsed = parse_sheet_id(sheet_id)
    if not parsed:
        raise ValueError("That doesn't look like a Google Sheets URL or spreadsheet ID.")
    data = _read_settings_file(path)
    data["sheet_id"] = parsed
    _write_settings_file(data, path)
    return parsed


def clear_sheet_id(path=SETTINGS_PATH):
    """Remove the runtime override so secrets / default apply again."""
    data = _read_settings_file(path)
    data.pop("sheet_id", None)
    _write_settings_file(data, path)


def check_admin_login(username, password):
    """Constant-time comparison against the configured admin credentials."""
    expected_user = str(get_secret("admin_username", DEFAULT_ADMIN_USERNAME))
    expected_pass = str(get_secret("admin_password", DEFAULT_ADMIN_PASSWORD))
    user_ok = hmac.compare_digest((username or "").strip().encode(), expected_user.encode())
    pass_ok = hmac.compare_digest((password or "").encode(), expected_pass.encode())
    return user_ok and pass_ok
