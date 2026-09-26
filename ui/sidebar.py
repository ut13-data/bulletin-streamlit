"""Sidebar: user, new chat, search, chats grouped by day (with rename and delete), log out."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from services import auth


def user_tz() -> ZoneInfo:
    try:
        return ZoneInfo(st.context.timezone or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def day_group(ts: datetime) -> str:
    today = datetime.now(user_tz()).date()
    day = ts.astimezone(user_tz()).date()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return "Older"


def open_chat(chat_id: str | None):
    """Switch chats. The chat id also goes in the URL, so after logging in again it reopens."""
    st.session_state["current_chat"] = chat_id
    if chat_id:
        st.query_params["chat"] = chat_id
    else:
        st.query_params.pop("chat", None)


def _chat_row(store, chat: dict, is_current: bool):
    left, right = st.columns([0.84, 0.16], vertical_alignment="center")
    left.button(chat["title"], key=f"open-{chat['id']}", on_click=open_chat, args=(chat["id"],),
                type="tertiary" if is_current else "secondary", width="stretch")
    with right.popover("", icon=":material/more_vert:"):
        new_title = st.text_input("Rename", value=chat["title"], key=f"title-{chat['id']}")
        if st.button("Save name", key=f"save-{chat['id']}", width="stretch"):
            store.rename_chat(chat["id"], new_title)
            st.rerun()
        st.divider()
        sure = st.checkbox("Yes, delete this chat", key=f"sure-{chat['id']}")
        if st.button("Delete", key=f"del-{chat['id']}", disabled=not sure, width="stretch"):
            store.delete_chat(chat["id"])
            if is_current:
                open_chat(None)
            st.rerun()


def render(store, user: dict):
    with st.sidebar:
        st.markdown("### bUlleTin")
        st.markdown(f'<div class="sidebar-user">Signed in as {user["name"]}</div>', unsafe_allow_html=True)
        if st.button("New chat", icon=":material/add:", type="primary", width="stretch"):
            open_chat(None)
        search = st.text_input("Search", placeholder="Search chats", label_visibility="collapsed")

        chats = [c for c in store.list_chats() if search.lower() in c["title"].lower()]
        current_group = None
        for c in chats:
            group = day_group(c["updated_at"])
            if group != current_group:
                st.caption(group)
                current_group = group
            _chat_row(store, c, c["id"] == st.session_state.get("current_chat"))
        if not chats and search:
            st.caption("No chats match.")

        st.divider()
        if st.button("Log out", icon=":material/logout:", width="stretch"):
            auth.sign_out()
            st.query_params.clear()
            st.rerun()
