from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Emoji → subteam mapping
SUBTEAM_EMOJIS = {
    "hammer_and_wrench": "Mechanical",
    "computer": "Software",
    "art": "Loco",
    "briefcase": "Executive",
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


def parse_slack_link(link: str):
    """Extract channel ID and timestamp from a Slack message link."""
    parts = link.rstrip("/").split("/")
    channel_id = parts[-2]
    ts = parts[-1].lstrip("p")
    timestamp = ts[:-6] + "." + ts[-6:]
    return channel_id, timestamp


def get_all_reactions(token: str, link: str) -> dict:
    """
    Returns a dict of {emoji_name: [user_id, ...]} for all reactions on the message.
    """
    client = WebClient(token=token)
    channel_id, timestamp = parse_slack_link(link)
    try:
        response = client.reactions_get(channel=channel_id, timestamp=timestamp)
        reactions = response["message"].get("reactions", [])
        return {r["name"]: r["users"] for r in reactions}
    except SlackApiError as e:
        return {"error": str(e)}


def get_user_real_name(token: str, user_id: str) -> str:
    """Resolve a Slack user ID to their real name."""
    client = WebClient(token=token)
    try:
        response = client.users_info(user=user_id)
        return response["user"]["profile"]["real_name"]
    except SlackApiError:
        return user_id


def get_attendance_by_subteam(token: str, link: str) -> dict:
    """
    Returns:
    {
        "Mechanical": [list of real names],
        "Software": [...],
        "Loco": [...],
        "Executive": [...],
        "wont_attend": [list of real names],
        "error": "..." (only if API call failed)
    }
    """
    reactions = get_all_reactions(token, link)

    if "error" in reactions:
        return reactions

    result = {subteam: [] for subteam in SUBTEAM_EMOJIS.values()}
    result["wont_attend"] = []

    for emoji, users in reactions.items():
        if emoji in SUBTEAM_EMOJIS:
            subteam = SUBTEAM_EMOJIS[emoji]
            names = [get_user_real_name(token, uid) for uid in users]
            result[subteam].extend(names)
        elif emoji in WONT_ATTEND_EMOJIS:
            names = [get_user_real_name(token, uid) for uid in users]
            result["wont_attend"].extend(names)

    return result
