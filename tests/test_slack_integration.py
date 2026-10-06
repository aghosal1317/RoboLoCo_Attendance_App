"""
Slack parsing tests. No network: slack_sdk.WebClient is replaced by a fake
that replays a canned reactions_get response.
"""
import pytest

import slack_integration as si

# The real 7/23 WVRox-prep message: Mech / Software / Leadership only, no Loco.
SUBSET_TEXT = (
    "<!channel> Attendance for Thursday's meeting, 7/23. This meeting is for WVRox prep "
    "and is from 3-7pm. Mech, react :hammer_and_wrench: if you will attend. "
    "Software react :computer:. Leadership, react :briefcase:. "
    "If you will not be in attendance, react :-1:."
)


class FakeSlackClient:
    def __init__(self, text, reactions, users=None, token=None):
        self._text = text
        self._reactions = reactions
        self._users = users or {}
        self.users_info_calls = 0

    def reactions_get(self, channel, timestamp):
        return {"message": {"text": self._text,
                            "reactions": [{"name": n, "users": u} for n, u in self._reactions.items()]}}

    def users_info(self, user):
        self.users_info_calls += 1
        return {"user": {"profile": {"real_name": self._users.get(user, user)}}}


@pytest.fixture
def fake_slack(monkeypatch):
    holder = {}

    def install(text, reactions, users=None):
        client = FakeSlackClient(text, reactions, users)
        monkeypatch.setattr(si, "WebClient", lambda token=None: client)
        holder["client"] = client
        return client

    install.holder = holder
    return install


# ── find_invited_subteams ───────────────────────────────────────────────────

def test_invited_from_colon_codes():
    assert si.find_invited_subteams(SUBSET_TEXT) == {"Mechanical", "Software", "Executive"}


def test_invited_from_unicode_glyphs():
    text = "Mech, react \U0001F6E0️. Software react \U0001F4BB. Leadership, react \U0001F4BC. Else \U0001F44E."
    assert si.find_invited_subteams(text) == {"Mechanical", "Software", "Executive"}


def test_invited_full_team_message():
    text = "Everyone react: :hammer_and_wrench: :computer: :art: :briefcase:"
    assert si.find_invited_subteams(text) == {"Mechanical", "Software", "Loco", "Executive"}


def test_invited_plain_wrench_also_means_mech():
    assert si.find_invited_subteams("Mech react :wrench:") == {"Mechanical"}


def test_invited_empty_when_no_emoji():
    assert si.find_invited_subteams("Meeting tomorrow at 3, see you there") == set()
    assert si.find_invited_subteams(None) == set()


# ── get_attendance_by_subteam ───────────────────────────────────────────────

def test_subset_message_parses_invited_and_names(fake_slack):
    fake_slack(
        SUBSET_TEXT,
        {"hammer_and_wrench": ["U1", "U2"], "computer": ["U3"],
         "briefcase": ["U4"], "-1": ["U5"], "-1::skin-tone-3": ["U6"]},
        {"U1": "Srin Dasari", "U2": "Ethan Burget", "U3": "Aneesh Ghosal",
         "U4": "JD Queen", "U5": "Julia Miller", "U6": "Adam Youmans"},
    )
    r = si.get_attendance_by_subteam("tok", "https://x.slack.com/archives/C1/p1700000000000000")

    assert r["invited"] == {"Mechanical", "Software", "Executive"}
    assert "Loco" not in r["invited"]
    assert sorted(r["Mechanical"]) == ["Ethan Burget", "Srin Dasari"]
    assert r["Software"] == ["Aneesh Ghosal"]
    assert r["Executive"] == ["JD Queen"]
    assert r["Loco"] == []
    # both plain and skin-toned thumbs-down count as won't-attend
    assert sorted(r["wont_attend"]) == ["Adam Youmans", "Julia Miller"]


def test_invited_is_never_inferred_from_who_reacted(fake_slack):
    """
    Regression: the invite list used to fall back to "whichever subteams
    reacted" when the text had no emoji. A subteam where nobody reacted then
    looked uninvited, so all of its members were recorded O ("didn't apply")
    instead of A. Empty means "couldn't tell", and callers assume everyone.
    """
    fake_slack("Practice today, react if coming", {"computer": ["U1"], "art": ["U2"]})
    r = si.get_attendance_by_subteam("tok", "https://x.slack.com/archives/C1/p1700000000000000")
    assert r["invited"] == set()


def test_alternative_emoji_for_the_same_group_are_recognised():
    """A message using :hammer: must not make Mechanical look uninvited."""
    for text in (":hammer:", ":hammer_and_wrench:", ":wrench:", ":tools:",
                 "\U0001F528", "\U0001F6E0\uFE0F"):
        assert si.find_invited_subteams(f"Build react {text}") == {"Mechanical"}
    for text in (":art:", ":artist_palette:", ":paintbrush:", "\U0001F3A8"):
        assert si.find_invited_subteams(f"Loco react {text}") == {"Loco"}
    for text in (":computer:", ":laptop:", "\U0001F4BB"):
        assert si.find_invited_subteams(f"Software react {text}") == {"Software"}


def test_text_emoji_wins_over_reactions(fake_slack):
    """Loco was invited even though nobody from Loco reacted yet."""
    fake_slack(SUBSET_TEXT + " :art:", {"computer": ["U1"]})
    r = si.get_attendance_by_subteam("tok", "https://x.slack.com/archives/C1/p1700000000000000")
    assert r["invited"] == {"Mechanical", "Software", "Executive", "Loco"}


def test_user_names_are_cached_not_refetched(fake_slack):
    client = fake_slack(SUBSET_TEXT, {"computer": ["U1", "U1", "U2"], "briefcase": ["U1"]})
    si.get_attendance_by_subteam("tok", "https://x.slack.com/archives/C1/p1700000000000000")
    assert client.users_info_calls == 2   # U1 and U2, once each


def test_api_error_is_surfaced(monkeypatch):
    from slack_sdk.errors import SlackApiError

    class Boom:
        def reactions_get(self, channel, timestamp):
            raise SlackApiError("message_not_found", response={"error": "message_not_found"})
    monkeypatch.setattr(si, "WebClient", lambda token=None: Boom())
    r = si.get_attendance_by_subteam("tok", "https://x.slack.com/archives/C1/p1700000000000000")
    assert "error" in r


def test_parse_slack_link():
    assert si.parse_slack_link("https://team.slack.com/archives/C123ABC/p1753300000123456") == \
        ("C123ABC", "1753300000.123456")


# ── The 9/29 workshop message: all six groups, incl. Mentors and Coaches ────

WORKSHOP_TEXT = (
    "<!channel> Attendance for Tomorrow's meeting/workshop, 9/29. This meeting is for "
    "Workshops/prep. The meeting is from 5-7pm. Build, react :hammer_and_wrench: if you will "
    "attend. Programming, react :computer:. Loco react :art:. Leadership, react :briefcase:. "
    "Mentors react :memo: if you are attending. Coaches react :school: if you can attend. "
    "If you will not be in attendance, react :-1:."
)


def test_workshop_message_invites_every_group():
    assert si.find_invited_subteams(WORKSHOP_TEXT) == {
        "Mechanical", "Software", "Loco", "Executive", "Mentors", "Coaches"}


def test_workshop_message_as_unicode_glyphs():
    text = ("Build, react \U0001F6E0️. Programming, react \U0001F4BB. Loco react \U0001F3A8. "
            "Leadership, react \U0001F4BC. Mentors react \U0001F4DD. Coaches react \U0001F3EB.")
    assert si.find_invited_subteams(text) == {
        "Mechanical", "Software", "Loco", "Executive", "Mentors", "Coaches"}


def test_mentors_invited_even_with_zero_reactions(fake_slack):
    """
    The real 9/29 message: 📝 got no reactions at all. Reading the invite list
    off reactions would wrongly conclude Mentors weren't asked and mark them absent.
    """
    fake_slack(WORKSHOP_TEXT, {
        "briefcase": [f"E{i}" for i in range(11)],
        "hammer_and_wrench": [f"M{i}" for i in range(14)],
        "-1": [f"N{i}" for i in range(12)],
        "computer": [f"S{i}" for i in range(10)],
        "art": ["L1", "L2"],
        "school": ["C1", "C2"],
    })
    r = si.get_attendance_by_subteam("tok", "https://x.slack.com/archives/C1/p1700000000000000")

    assert "Mentors" in r["invited"]
    assert r["Mentors"] == []
    # counts line up with the reaction bar on the real message
    assert (len(r["Executive"]), len(r["Mechanical"]), len(r["Software"]),
            len(r["Loco"]), len(r["Coaches"]), len(r["wont_attend"])) == (11, 14, 10, 2, 2, 12)


def test_coach_and_mentor_emoji_recognised():
    import data_loader as dl
    assert si.SUBTEAM_EMOJIS["school"] == "Coaches"
    assert si.SUBTEAM_EMOJIS["memo"] == "Mentors"
    assert si.SUBTEAM_EMOJIS["pencil"] == "Mentors"
    # both are recorded; only coaches are exempt from the 70% threshold
    assert "Coaches" in dl.NON_THRESHOLD_SUBTEAMS
    assert "Mentors" not in dl.NON_THRESHOLD_SUBTEAMS


def test_build_and_programming_wording_maps_to_roster_names():
    """Messages say Build/Programming; the roster says Mechanical/Software."""
    assert si.find_invited_subteams("Build, react :hammer_and_wrench:") == {"Mechanical"}
    assert si.find_invited_subteams("Programming, react :computer:") == {"Software"}
    assert si.SUBTEAM_ALIASES["Mechanical"] == "Mechanical / Build"
    assert si.SUBTEAM_ALIASES["Software"] == "Software / Programming"


# ── Reading the meeting details out of the message ──────────────────────────

from datetime import date as _date

TODAY = _date(2026, 10, 6)


def test_finds_date_in_both_real_messages():
    assert si.find_meeting_date(SUBSET_TEXT, TODAY) == _date(2026, 7, 23)
    assert si.find_meeting_date(WORKSHOP_TEXT, TODAY) == _date(2026, 9, 29)


def test_time_ranges_are_not_mistaken_for_dates():
    """'from 3-7pm' and 'from 5-7pm' must not parse as 3/7 or 5/7."""
    assert si.find_meeting_date("The meeting is from 3-7pm, no date given", TODAY) is None
    assert si.find_meeting_date("Meeting 9/29. The meeting is from 5-7pm.", TODAY) == _date(2026, 9, 29)


def test_meeting_slash_workshop_is_not_a_date():
    assert si.find_meeting_date("Attendance for Tomorrow's meeting/workshop", TODAY) is None


def test_year_is_inferred_as_the_nearest_one():
    # read in January, "12/20" is the December just gone
    assert si.find_meeting_date("Meeting 12/20", _date(2026, 1, 5)) == _date(2025, 12, 20)
    # read in December, "1/10" is the January coming
    assert si.find_meeting_date("Meeting 1/10", _date(2025, 12, 20)) == _date(2026, 1, 10)


def test_explicit_year_is_respected():
    assert si.find_meeting_date("Practice 1/10/26", TODAY) == _date(2026, 1, 10)
    assert si.find_meeting_date("Practice 1/10/2026", TODAY) == _date(2026, 1, 10)


def test_impossible_dates_are_skipped():
    assert si.find_meeting_date("Meeting 13/45", TODAY) is None
    assert si.find_meeting_date("Meeting 2/29", TODAY) is None   # no leap year nearby


def test_no_date_at_all():
    assert si.find_meeting_date("Practice tonight, be there", TODAY) is None
    assert si.find_meeting_date("", TODAY) is None
    assert si.find_meeting_date(None, TODAY) is None


