import streamlit as st
from data_loader import inspect_sheet, get_service_account_email
from settings import (
    get_sheet_id, get_sheet_id_source, set_sheet_id, clear_sheet_id,
    parse_sheet_id, sheet_url, check_admin_login, DEFAULT_SHEET_ID,
)

st.title("Settings — Season Spreadsheet")
st.caption("Where the app reads and writes attendance. Change this once per season.")

# ----------------------------
# Current configuration
# ----------------------------
current_id = get_sheet_id()
source_label = {
    "settings file": "set on this page",
    "secrets": "set in Streamlit secrets (`SHEET_ID`)",
    "default": "built-in default",
}[get_sheet_id_source()]
sa_email = get_service_account_email()

with st.container(border=True):
    st.markdown(f"**Active spreadsheet:** [{current_id}]({sheet_url(current_id)})")
    st.caption(f"Source: {source_label}")
    if sa_email:
        st.markdown(f"**Service account email** (share every sheet with this as *Editor*):")
        st.code(sa_email, language=None)
    else:
        st.warning("No Google service account credentials found — the app can't reach any sheet.")

# ----------------------------
# From-scratch instructions (visible to everyone)
# ----------------------------
st.subheader("Setting up a new season's spreadsheet from scratch")

st.markdown(
    """
**1. Create the sheet.** Go to [sheets.google.com](https://sheets.google.com) → *Blank spreadsheet*.
Name it something like `26-27 RoboLoCo Attendance`. The app only reads the **first tab**, so keep the roster there.

**2. Fill in row 1 (the header row) exactly like this:**
"""
)
st.table(
    {
        "A": ["Last Name"],
        "B": ["First Name"],
        "C": ["Full Name"],
        "D": ["% Meetings Attended"],
        "E": ["Subteam"],
    }
)
st.markdown(
    """
- Column **A must be last names and B must be first names** — the app goes by position for those two.
- **`Subteam`** must be spelled exactly like that. Values: `Executive`, `Loco`, `Mechanical`, `Software`.
- `Full Name` and `% Meetings Attended` can be left empty — the app fills them in.
- **Don't add any date columns.** They're created automatically the first time attendance is taken
  (`MM/DD/YY`, with a second `MM/DD/YY.1` column for Saturday double sessions).

**3. Add one row per member** starting on row 2. Names must be **unique**, and `First Last` must match the
member's Slack display name for Slack Sync to work. Leave coaches off — the app ignores/removes them.

> *Alternative layout:* you can instead put a subteam name (`Executive`, `Loco`, …) alone in column A as a
> section-header row with that subteam's members underneath and no `Subteam` column. The app reads that too,
> but the first time it saves it rewrites the sheet into the layout above and drops the section rows.

**4. Share it with the app.** Click **Share** (top right) → paste the service account email shown above →
set to **Editor** → untick *Notify* → **Share**. Without this the app gets a permission error.

**5. Point the app at it.** Log in below, paste the sheet's URL, click **Test connection**, check that the
member count and subteams look right, then **Switch to this sheet**.

**6. Make it stick across restarts.** The app is hosted on Streamlit Community Cloud, whose disk is wiped on
every reboot/redeploy, so a change made here lasts until the next reboot. To make it permanent: open
[share.streamlit.io](https://share.streamlit.io) → the app → **⋮ → Settings → Secrets**, add the line the
page shows you after switching (`SHEET_ID = "..."`), and **Save**.

**7. Afterwards:** regenerate QR codes on the *Generate QR Codes* page (codes encode the member's name),
and check the *Dashboard* loads. Last season's data stays untouched in the old sheet.
"""
)

st.divider()

# ----------------------------
# Admin login
# ----------------------------
st.subheader("Change the active spreadsheet")

if not st.session_state.get("admin_authed"):
    with st.form("admin_login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        if check_admin_login(username, password):
            st.session_state.admin_authed = True
            st.rerun()
        else:
            st.error("Incorrect username or password.")
    st.stop()

if st.button("Log out"):
    st.session_state.admin_authed = False
    st.session_state.pop("sheet_test", None)
    st.rerun()

new_input = st.text_input(
    "New spreadsheet URL or ID",
    placeholder="https://docs.google.com/spreadsheets/d/…/edit",
)
new_id = parse_sheet_id(new_input)

test_col, switch_col = st.columns(2)
with test_col:
    test_clicked = st.button("Test connection", disabled=not new_id)
with switch_col:
    switch_clicked = st.button("Switch to this sheet", type="primary", disabled=not new_id)

if new_input and not new_id:
    st.error("That doesn't look like a Google Sheets URL or spreadsheet ID.")

if test_clicked:
    with st.spinner("Reading the sheet…"):
        try:
            st.session_state.sheet_test = (new_id, inspect_sheet(new_id))
        except Exception as e:
            st.session_state.sheet_test = (new_id, e)

if st.session_state.get("sheet_test") and st.session_state.sheet_test[0] == new_id:
    _, result = st.session_state.sheet_test
    if isinstance(result, Exception):
        st.error(f"Couldn't read that sheet: **{type(result).__name__}** — {result}")
        st.info(f"Most common cause: the sheet isn't shared with `{sa_email or 'the service account'}` as Editor.")
    else:
        st.success(f"Connected to **{result['title']}** (tab: *{result['worksheet']}*)")
        m1, m2 = st.columns(2)
        m1.metric("Members", result["members"])
        m2.metric("Date columns", result["date_columns"])
        st.caption(f"Layout detected: {result['layout']}")
        if result["subteams"]:
            st.write("Subteams:", ", ".join(f"{k} ({v})" for k, v in result["subteams"].items()))
        for w in result["warnings"]:
            st.warning(w)

if switch_clicked:
    try:
        saved_id = set_sheet_id(new_id)
    except ValueError as e:
        st.error(str(e))
    else:
        st.success(f"The app now uses [{saved_id}]({sheet_url(saved_id)}). Every page will load from it on next refresh.")
        st.info("To keep this after the app restarts, add this line to the app's **Secrets** on Streamlit Cloud (step 6 above):")
        st.code(f'SHEET_ID = "{saved_id}"', language="toml")

with st.expander("Reset to the built-in default sheet"):
    st.caption(f"Removes the override set on this page. The app will use the `SHEET_ID` secret if set, otherwise `{DEFAULT_SHEET_ID}`.")
    if st.button("Reset"):
        clear_sheet_id()
        st.success("Reset. Refresh the page to see the active sheet.")
