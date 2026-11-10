"""
Rotating 4-digit codes for check-in / check-out.

A static QR at the door opens the check-in page; that alone proves nothing,
because the link can be forwarded. The code shown on the kiosk screen is what
proves the student is in the room — it changes every ROTATION_SECONDS, and is
derived on the server from a secret the browser never sees.

    code = HMAC(SECRET, "<meeting_date>|<window>|<direction>")  -> 4 digits
    window = floor(server_epoch / ROTATION_SECONDS)

The previous window is also accepted, so someone who started typing just before
a rollover isn't punished for being slow.
"""
import hashlib
import hmac
from datetime import datetime, timezone

from settings import get_secret

DEFAULT_ROTATION_SECONDS = 30

# Used only when CHECKIN_SECRET is unset, so the app still runs locally. Codes
# built from it are guessable by anyone with the source, so the kiosk warns.
_DEV_SECRET = "roboloco-dev-secret-change-me"

DIRECTIONS = ("in", "out")


def get_secret_key():
    return str(get_secret("CHECKIN_SECRET") or _DEV_SECRET)


def using_dev_secret():
    """True when no CHECKIN_SECRET is configured — the kiosk says so out loud."""
    return not get_secret("CHECKIN_SECRET")


def get_rotation_seconds():
    try:
        value = int(get_secret("ROTATION_SECONDS") or DEFAULT_ROTATION_SECONDS)
    except (TypeError, ValueError):
        return DEFAULT_ROTATION_SECONDS
    return value if value > 0 else DEFAULT_ROTATION_SECONDS


def _epoch(now=None):
    if now is None:
        return datetime.now(timezone.utc).timestamp()
    if isinstance(now, datetime):
        if now.tzinfo is None:                      # treat naive times as UTC
            now = now.replace(tzinfo=timezone.utc)
        return now.timestamp()
    return float(now)


def current_window(now=None, rotation_seconds=None):
    """Which rotation window the server is in right now."""
    rotation_seconds = rotation_seconds or get_rotation_seconds()
    return int(_epoch(now) // rotation_seconds)


def seconds_remaining(now=None, rotation_seconds=None):
    """Seconds until the code changes — drives the kiosk countdown bar."""
    rotation_seconds = rotation_seconds or get_rotation_seconds()
    return rotation_seconds - (_epoch(now) % rotation_seconds)


def code_for_window(window, direction, meeting_date, secret=None):
    """The 4-digit code for one window. Pure: same inputs, same code."""
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
    secret = secret if secret is not None else get_secret_key()
    message = f"{meeting_date}|{window}|{direction}".encode()
    digest = hmac.new(str(secret).encode(), message, hashlib.sha256).digest()
    return f"{int.from_bytes(digest[:4], 'big') % 10000:04d}"


def current_code(direction, meeting_date, now=None, rotation_seconds=None, secret=None):
    window = current_window(now, rotation_seconds)
    return code_for_window(window, direction, meeting_date, secret)


def verify_code(entered, direction, meeting_date, now=None,
                rotation_seconds=None, secret=None):
    """
    True if `entered` is the code for the current window or the one before it.
    Compared in constant time; anything else (older, future, malformed) fails.
    """
    entered = str(entered or "").strip()
    if not entered.isdigit() or len(entered) != 4:
        return False

    window = current_window(now, rotation_seconds)
    for candidate_window in (window, window - 1):
        expected = code_for_window(candidate_window, direction, meeting_date, secret)
        if hmac.compare_digest(entered, expected):
            return True
    return False
