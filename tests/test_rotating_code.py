"""
The rotating code is the whole security story: a forwarded link is useless
without a code that is only visible on the screen in the shop. These tests pin
that behaviour — current works, previous works, older and wrong fail.
"""
from datetime import datetime, timezone

import pytest

import rotating_code as rc

SECRET = "test-secret"
MEETING = "20261109-170000"
T0 = datetime(2026, 11, 9, 17, 30, 0, tzinfo=timezone.utc)


def at(seconds):
    return T0.timestamp() + seconds


def code(direction="in", now=None, secret=SECRET):
    return rc.current_code(direction, MEETING, now=now, rotation_seconds=30, secret=secret)


# ── generation ──────────────────────────────────────────────────────────────

def test_code_is_four_digits():
    c = code()
    assert len(c) == 4 and c.isdigit()


def test_code_is_stable_within_a_window():
    assert code(now=at(0)) == code(now=at(29))


def test_code_changes_at_the_window_boundary():
    assert code(now=at(0)) != code(now=at(30))


def test_check_in_and_check_out_codes_differ():
    assert code("in", now=at(0)) != code("out", now=at(0))


def test_code_depends_on_the_meeting():
    a = rc.code_for_window(100, "in", "meeting-a", secret=SECRET)
    b = rc.code_for_window(100, "in", "meeting-b", secret=SECRET)
    assert a != b


def test_code_depends_on_the_secret():
    a = rc.code_for_window(100, "in", MEETING, secret="one")
    b = rc.code_for_window(100, "in", MEETING, secret="two")
    assert a != b


def test_unknown_direction_is_rejected():
    with pytest.raises(ValueError):
        rc.code_for_window(1, "sideways", MEETING, secret=SECRET)


# ── verification: the three cases from the brief ────────────────────────────

def test_current_code_is_accepted():
    now = at(5)
    assert rc.verify_code(code(now=now), "in", MEETING,
                          now=now, rotation_seconds=30, secret=SECRET)


def test_previous_code_is_accepted_for_slow_typers():
    typed = code(now=at(25))          # read just before the rollover
    later = at(35)                    # submitted just after it
    assert rc.verify_code(typed, "in", MEETING,
                          now=later, rotation_seconds=30, secret=SECRET)


def test_two_windows_old_is_rejected():
    stale = code(now=at(0))
    later = at(70)                    # two rotations on
    assert not rc.verify_code(stale, "in", MEETING,
                              now=later, rotation_seconds=30, secret=SECRET)


def test_wrong_code_is_rejected():
    now = at(5)
    real = code(now=now)
    wrong = f"{(int(real) + 1) % 10000:04d}"
    assert not rc.verify_code(wrong, "in", MEETING,
                              now=now, rotation_seconds=30, secret=SECRET)


def test_check_in_code_does_not_work_for_check_out():
    """Otherwise a student could check out from home using the check-in code."""
    now = at(5)
    assert not rc.verify_code(code("in", now=now), "out", MEETING,
                              now=now, rotation_seconds=30, secret=SECRET)


def test_malformed_input_is_rejected():
    now = at(5)
    for bad in ("", None, "12", "12345", "abcd", "12 3", "1.23"):
        assert not rc.verify_code(bad, "in", MEETING,
                                  now=now, rotation_seconds=30, secret=SECRET)


def test_a_code_from_another_meeting_is_rejected():
    now = at(5)
    other = rc.current_code("in", "some-other-meeting", now=now,
                            rotation_seconds=30, secret=SECRET)
    assert not rc.verify_code(other, "in", MEETING,
                              now=now, rotation_seconds=30, secret=SECRET)


# ── countdown ───────────────────────────────────────────────────────────────

def test_seconds_remaining_counts_down_within_the_window():
    assert rc.seconds_remaining(now=at(0), rotation_seconds=30) == 30
    assert rc.seconds_remaining(now=at(10), rotation_seconds=30) == 20
    assert rc.seconds_remaining(now=at(29), rotation_seconds=30) == 1


def test_rotation_seconds_is_configurable(monkeypatch):
    monkeypatch.setattr(rc, "get_secret", lambda k, d=None: 60 if k == "ROTATION_SECONDS" else d)
    assert rc.get_rotation_seconds() == 60


def test_bad_rotation_setting_falls_back_to_the_default(monkeypatch):
    for bad in ("abc", "", 0, -5):
        monkeypatch.setattr(rc, "get_secret", lambda k, d=None, v=bad: v if k == "ROTATION_SECONDS" else d)
        assert rc.get_rotation_seconds() == rc.DEFAULT_ROTATION_SECONDS


def test_dev_secret_is_detectable(monkeypatch):
    monkeypatch.setattr(rc, "get_secret", lambda k, d=None: None)
    assert rc.using_dev_secret()
    monkeypatch.setattr(rc, "get_secret", lambda k, d=None: "real" if k == "CHECKIN_SECRET" else d)
    assert not rc.using_dev_secret()
