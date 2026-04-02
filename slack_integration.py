from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

def parse_slack_link(link: str):
    """Extract channel ID and timestamp from a Slack message link."""
    # Link format: https://yourteam.slack.com/archives/C12345/p1234567890
    parts = link.rstrip("/").split("/")
    channel_id = parts[-2]
    ts = parts[-1].lstrip("p")
    timestamp = ts[:-6] + "." + ts[-6:]  # convert to Slack ts format
    return channel_id, timestamp

def get_reactors(token: str, link: str, emoji: str = "white_check_mark"):
    return ['U001', 'U002', 'U003']
    #fake data until I get permissions from coaches
    '''
    client = WebClient(token=token)
    channel_id, timestamp = parse_slack_link(link)
    try:
        response = client.reactions_get(channel=channel_id, timestamp=timestamp)
        reactions = response["message"].get("reactions", [])
        for r in reactions:
            if r["name"] == emoji:
                return r["users"]  # list of Slack user IDs
        return []
    except SlackApiError as e:
        return {"error": str(e)}
    '''

slack_to_name = {
    "U001": "Eshan Nayak",
    "U002": "Brian Tay",
    "U003": "Aarav Joshi"
}

def get_user_name(token: str, user_id: str):
    client = WebClient(token=token)
    response = client.users_info(user=user_id)
    return response["user"]["real_name"]