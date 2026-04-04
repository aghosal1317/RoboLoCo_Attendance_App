import streamlit as st
from slack_integration import get_reactors, get_user_name

token = st.secrets["SLACK_TOKEN"]  # store in .streamlit/secrets.toml

st.title("Sync from Slack")
st.warning("🚧 This feature is coming soon. Slack Bot integration is in progress.")
link = st.text_input("Paste Slack message link")
emoji = st.text_input("Reaction emoji to count", value="white_check_mark (do visuals)")

if st.button("Fetch Attendance"):
    with st.spinner("Fetching..."):
        user_ids = get_reactors(token, link, emoji)
        if isinstance(user_ids, dict):  # error
            st.error(user_ids["error"])
        else:
            names = [get_user_name(token, uid) for uid in user_ids]
            st.success(f"Found {len(names)} present")
            st.write(names)
            # TODO: call append_attendance() here