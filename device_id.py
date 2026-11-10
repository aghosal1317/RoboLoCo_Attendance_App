"""
A long-lived random id per phone, used only to flag one device checking in
several students. Never blocks anyone; it's a hint for a human to look at.

Streamlit can read cookies but has no API to set one, so this leans on the
optional extra-streamlit-components CookieManager. If that package is missing
or misbehaves on Streamlit Cloud, every function here degrades to "no device
id" — check-in keeps working and you simply lose the flag. Losing a nice-to-have
signal is much better than the check-in page failing at the door.
"""
import uuid

import streamlit as st

COOKIE_NAME = "roboloco_device"


def _manager():
    try:
        import extra_streamlit_components as stx
    except Exception:
        return None
    try:
        if "_device_cookie_mgr" not in st.session_state:
            st.session_state._device_cookie_mgr = stx.CookieManager(key="device_cookie_mgr")
        return st.session_state._device_cookie_mgr
    except Exception:
        return None


def get_device_id():
    """
    The id for this browser, creating one on first visit. Returns "" when
    cookies aren't available, which callers must treat as "unknown device".
    """
    manager = _manager()
    if manager is None:
        return str(st.session_state.get("_device_id_fallback", ""))

    try:
        existing = manager.get(COOKIE_NAME)
    except Exception:
        existing = None

    if existing:
        return str(existing)

    new_id = uuid.uuid4().hex
    try:
        manager.set(COOKIE_NAME, new_id, key=f"set_{COOKIE_NAME}")
    except Exception:
        st.session_state._device_id_fallback = new_id
    return new_id
