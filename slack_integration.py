import re
from datetime import date

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Emoji → subteam mapping. Keys are Slack emoji *names* (what the API returns
# for reactions); the unicode glyphs below map back onto the same names so we
# can also read the emoji out of the message text.
SUBTEAM_EMOJIS = {
    "hammer_and_wrench": "Mechanical",
    "wrench": "Mechanical",
    "computer": "Software",
    "art": "Loco",
    "briefcase": "Executive",
    "memo": "Mentors",
    "pencil": "Mentors",      # Slack renders :pencil: as 📝 too
    "school": "Coaches",
}

# How a group is worded in meeting messages vs. what the roster calls it.
# Messages say "Build"/"Programming"/"Leadership"; the sheet says
# "Mechanical"/"Software"/"Executive". Display only — the roster name is
# canonical everywhere data is written.
SUBTEAM_ALIASES = {
    "Mechanical": "Mechanical / Build",
    "Software": "Software / Programming",
    "Executive": "Executive / Leadership",
}

# Unicode glyph → emoji name, for messages written with the emoji picker
# instead of :colon_codes:. Variation selectors are stripped before lookup.
_GLYPH_TO_NAME = {
    "\U0001F6E0": "hammer_and_wrench",
    "\U0001F527": "wrench",
    "\U0001F4BB": "computer",
    "\U0001F3A8": "art",
    "\U0001F4BC": "briefcase",
    "\U0001F4DD": "memo",
    "\U0001F3EB": "school",
    "\U0001F44E": "-1",
}

# All thumbs-down skin tone variants count as "won't attend"
WONT_ATTEND_EMOJIS = {
    "-1",
    "-1::skin-tone-2",
    "-1::skin-tone-3",
    "-1::skin-tone-4",
    "-1::skin-tone-5",
    "-1::skin-tone-6",
}


def _base_emoji(name):
    """'-1::skin-tone-3' → '-1' (skin tone variants are the same reaction)."""
    return str(name).split("::")[0]


def parse_slack_link(link: str):
    """Extract channel ID and timestamp from a Slack message link."""
    parts = link.rstrip("/").split("/")
    channel_id = parts[-2]
    ts = parts[-1].lstrip("p")
    timestamp = ts[:-6] + "." + ts[-6:]
    return channel_id, timestamp


def find_invited_subteams(text):
    """
    Which subteams a meeting message actually asks for, read off the emoji in
    its text — both ':hammer_and_wrench:' codes and 🛠 glyphs.

    Messages don't always invite the whole team ("Mech, react 🛠. Software react
    💻. Leadership, react 💼." leaves Loco out entirely), and members of a
    subteam that was never asked must not be marked absent.

    Returns a set of roster subteam names; empty if no emoji were found.
    """
    text = str(text or "")
    found = set()

    for name, subteam in SUBTEAM_EMOJIS.items():
        if f":{name}:" in text:
            found.add(subteam)

    for ch in text:
        name = _GLYPH_TO_NAME.get(ch)
        if name in SUBTEAM_EMOJIS:
            found.add(SUBTEAM_EMOJIS[name])

    return found


def get_message(token: str, link: str) -> dict:
    """
    Fetch one message with its reactions.
    Returns {"text": str, "reactions": {emoji_name: [user_id, ...]}}
    or {"error": "..."}.
    """
    client = WebClient(token=token)
    channel_id, timestamp = parse_slack_link(link)
    try:
        response = client.reactions_get(channel=channel_id, timestamp=timestamp)
        message = response["message"]
        return {
            "text": message.get("text", ""),
            "reactions": {r["name"]: r["users"] for r in message.get("reactions", [])},
        }
    except SlackApiError as e:
        return {"error": str(e)}


def get_all_reactions(token: str, link: str) -> dict:
    """{emoji_name: [user_id, ...]} for all reactions on the message."""
    result = get_message(token, link)
    return result if "error" in result else result["reactions"]


def _name_resolver(token: str):
    """users_info is one API call per user, so cache within a single sync."""
    client = WebClient(token=token)
    cache = {}

    def resolve(user_id):
        if user_id not in cache:
            try:
                cache[user_id] = client.users_info(user=user_id)["user"]["profile"]["real_name"]
            except SlackApiError:
                cache[user_id] = user_id
        return cache[user_id]

    return resolve


def get_user_real_name(token: str, user_id: str) -> str:
    """Resolve a Slack user ID to their real name."""
    return _name_resolver(token)(user_id)


def get_attendance_by_subteam(token: str, link: str) -> dict:
    """
    Returns:
    {
        "Mechanical": [real names],
        "Software": [...],
        "Loco": [...],
        "Executive": [...],
        "wont_attend": [real names who reacted 👎],
        "invited": {subteam names the message asked for},
        "text": the message text,
        "error": "..." (only if the API call failed)
    }

    'invited' comes from the emoji in the message text, falling back to the
    emoji people actually reacted with when the text has none.
    """
    message = get_message(token, link)
    if "error" in message:
        return message

    reactions = message["reactions"]
    resolve = _name_resolver(token)

    result = {subteam: [] for subteam in set(SUBTEAM_EMOJIS.values())}
    result["wont_attend"] = []

    reacted_subteams = set()
    for emoji, users in reactions.items():
        base = _base_emoji(emoji)
        if base in SUBTEAM_EMOJIS:
            subteam = SUBTEAM_EMOJIS[base]
            reacted_subteams.add(subteam)
            result[subteam].extend(resolve(uid) for uid in users)
        elif emoji in WONT_ATTEND_EMOJIS or base == "-1":
            result["wont_attend"].extend(resolve(uid) for uid in users)

    # Prefer what the message asked for; fall back to what people reacted with.
    result["invited"] = find_invited_subteams(message["text"]) or reacted_subteams
    result["text"] = message["text"]
    return result


# ── Reading the meeting details out of the message ──────────────────────────

# "7/23", "9/29", "12/20/25" — but not the "3-7pm" style time ranges, which
# have no slash, and not a bare number inside a longer run of digits.
_DATE_IN_TEXT_RE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])")


def find_meeting_date(text, today=None):
    """
    The meeting date named in a message — "Attendance for Thursday's meeting,
    7/23" → date(2026, 7, 23). Returns None if the message has no date.

    Messages almost never include the year, so the year is chosen to put the
    date nearest today: read in January, a "12/20" means the December just
    gone, not the one eleven months away.
    """
    today = today or date.today()

    for m in _DATE_IN_TEXT_RE.finditer(str(text or "")):
        month, day, year = int(m.group(1)), int(m.group(2)), m.group(3)
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue

        if year:
            y = int(year)
            y += 2000 if y < 100 else 0
            try:
                return date(y, month, day)
            except ValueError:
                continue

        best = None
        for y in (today.year - 1, today.year, today.year + 1):
            try:
                candidate = date(y, month, day)
            except ValueError:      # e.g. 2/29 in a non-leap year
                continue
            if best is None or abs((candidate - today).days) < abs((best - today).days):
                best = candidate
        if best is not None:
            return best

    return None

