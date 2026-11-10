"""
Kiosk screen — the laptop or TV in the shop.

Shows the rotating check-in and check-out codes. Students must read a code off
this screen to check in, so a forwarded link on its own does nothing. PIN-gated:
if anyone could open this from home the whole scheme is pointless.
"""
import streamlit as st

import session_log
from rotating_code import (
    current_code, seconds_remaining, get_rotation_seconds, using_dev_secret,
)
from settings import check_kiosk_pin

# How often the kiosk re-reads the log for the headcount. The codes update every
# second regardless; only this costs an API call.
SIGNED_IN_REFRESH_SECONDS = 20

st.title("Check-In Kiosk")

# ----------------------------
# PIN gate
# ----------------------------
if not st.session_state.get("kiosk_unlocked"):
    st.caption("Put this screen where everyone at the meeting can see it.")
    with st.form("kiosk_pin"):
        pin = st.text_input("Kiosk PIN", type="password")
        if st.form_submit_button("Unlock"):
            if check_kiosk_pin(pin):
                st.session_state.kiosk_unlocked = True
                st.rerun()
            else:
                st.error("Wrong PIN.")
    st.stop()

if using_dev_secret():
    st.error(
        "**CHECKIN_SECRET is not set**, so the codes come from the public default in the "
        "source and anyone reading the repo can generate them. Set it in Streamlit "
        "secrets before relying on this."
    )

# ----------------------------
# Result of ending a meeting — shown before the "no meeting open" branch
# below, which would otherwise st.stop() before you ever see who was left in.
# ----------------------------
if "kiosk_closed" in st.session_state:
    result = st.session_state.pop("kiosk_closed")
    auto = result.get("auto_checked_out", [])
    st.success(f"Meeting ended. {len(auto)} still signed in were checked out automatically.")
    if auto:
        st.caption("Auto-checked-out: " + ", ".join(auto))

# ----------------------------
# Meeting controls
# ----------------------------
meeting = session_log.active_meeting(cached=True)

if meeting is None:
    st.warning("No meeting is open. Check-in is closed until you start one.")
    label = st.text_input("Label (optional)", placeholder="e.g. WVRox prep")
    if st.button("Start meeting", type="primary"):
        session_log.open_meeting(opened_by="kiosk", label=label)
        st.rerun()
    st.stop()

head, control = st.columns([3, 1])
with head:
    st.caption(f"Meeting **{meeting['meeting_id']}**"
               + (f" — {meeting['label']}" if meeting.get("label") else "")
               + f" · opened {meeting['opened_at']} UTC")
with control:
    if st.button("End meeting"):
        result = session_log.close_meeting(meeting["meeting_id"])
        st.session_state["kiosk_closed"] = result
        st.rerun()

st.divider()


# ----------------------------
# The codes. This refreshes every second for the countdown, so it must make
# NO Sheets calls — current_code() is a pure HMAC. Reading the signed-in count
# here too would be ~120 API requests a minute against a 60/min quota, which
# rate-limits the kiosk and every student's phone along with it.
# ----------------------------
@st.fragment(run_every=1)
def code_display():
    rotation = get_rotation_seconds()
    left = seconds_remaining()
    date_key = meeting["meeting_id"]

    in_col, out_col = st.columns(2)
    for col, direction, title in ((in_col, "in", "CHECK IN"), (out_col, "out", "CHECK OUT")):
        with col:
            st.markdown(
                f"<div style='text-align:center'>"
                f"<div style='font-size:1.6rem;letter-spacing:.25em;opacity:.7'>{title}</div>"
                f"<div style='font-size:7rem;font-weight:800;line-height:1.05;"
                f"font-variant-numeric:tabular-nums'>"
                f"{current_code(direction, date_key)}</div></div>",
                unsafe_allow_html=True,
            )

    st.progress(max(0.0, min(1.0, left / rotation)))
    st.caption(f"New codes in {int(left)}s · rotates every {rotation}s")


# The headcount is the only part that needs the API, so it refreshes slowly.
@st.fragment(run_every=SIGNED_IN_REFRESH_SECONDS)
def signed_in_display():
    try:
        signed_in = session_log.open_sessions(meeting["meeting_id"], cached=True)
    except Exception as error:
        st.caption(f"Couldn't refresh the headcount just now ({type(error).__name__}). "
                   "Check-in is unaffected; this will retry shortly.")
        return

    st.markdown(
        f"<div style='text-align:center;font-size:2rem;margin-top:.5rem'>"
        f"Signed in: <strong>{len(signed_in)}</strong></div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Updates every {SIGNED_IN_REFRESH_SECONDS}s")
    with st.expander("Who's signed in"):
        st.write(", ".join(sorted(signed_in)) if signed_in else "Nobody yet.")


code_display()
signed_in_display()

# Best-effort: ask the browser not to sleep the screen mid-meeting.
# st.html can't run scripts and st.iframe takes a URL, so this needs the old
# components API, which is deprecated. Wrapped so that if it does disappear the
# kiosk keeps working and only loses the wake lock — set the shop laptop's
# display to never sleep as the reliable fix either way (see the README).
try:
    import streamlit.components.v1 as components

    components.html(
        """
        <script>
        (async () => {
          try {
            if ('wakeLock' in navigator) {
              let lock = await navigator.wakeLock.request('screen');
              document.addEventListener('visibilitychange', async () => {
                if (document.visibilityState === 'visible') {
                  try { lock = await navigator.wakeLock.request('screen'); } catch (e) {}
                }
              });
            }
          } catch (e) {}
        })();
        </script>
        """,
        height=0,
    )
except Exception:
    pass
