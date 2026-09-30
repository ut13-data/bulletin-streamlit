"""
Ask bUlleTin: Streamlit entry point.

  1. Not logged in  -> login / create account screen
  2. Logged in      -> sidebar (chats) + chat area
  3. On a question  -> check the 10-per-chat and 30-per-day limits, load this
                       chat's history from Supabase, run the agent, save both messages

Run:  streamlit run app.py
"""
from datetime import datetime

import streamlit as st

from agent.config import MAX_TURNS
from agent.graph import run_agent
from services import auth, quota
from services.store import SupabaseStore, history_for_agent
from ui import login, sidebar, styles
from ui.render import render_answer, user_bubble

st.set_page_config(page_title="Ask bUlleTin", page_icon="📊", layout="centered")
styles.apply()


SUGGESTIONS = [
    "What was revenue in FY24?",
    "Forecast revenue for the next 3 months",
    "Gross margin by category in FY24",
    "Top 5 products by revenue in FY24",
]


def greeting(name: str) -> str:
    hour = datetime.now(sidebar.user_tz()).hour
    part = "Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 17 else "Good evening"
    return f"{part}, {name}"


def get_store():
    """Chat storage for the logged-in user. (Tests swap this for an in-memory store.)"""
    user = auth.current_user()
    return SupabaseStore(auth.user_client(), user["id"])


# ============================================================
# 1. Login gate
# ============================================================

user = auth.current_user()
if not user:
    login.render()
    st.stop()

try:
    store = get_store()

    # Reopen the chat in the URL (e.g. after logging in again), if it's one of this user's chats.
    if "current_chat" not in st.session_state:
        wanted = st.query_params.get("chat")
        st.session_state["current_chat"] = wanted if wanted and store.chat_exists(wanted) else None

    sidebar.render(store, user)

    # ============================================================
    # 2. Chat area
    # ============================================================

    chat_id = st.session_state.get("current_chat")
    messages = store.get_messages(chat_id) if chat_id else []
    questions_asked = sum(1 for m in messages if m["role"] == "user")

    if not messages:
        st.markdown(f'<div class="greeting">{greeting(user["name"])}</div>', unsafe_allow_html=True)
        st.markdown('<div class="greeting-sub">Ask about revenue, margins, inventory, suppliers or forecasts.</div>',
                    unsafe_allow_html=True)
        with st.container(key="suggestions"):
            cols = st.columns(2)
            for i, text in enumerate(SUGGESTIONS):
                cols[i % 2].button(text, key=f"suggest-{i}", width="stretch",
                                   on_click=st.session_state.__setitem__, args=("pending_question", text))

    animate_key = st.session_state.pop("animate", None)   # only the newest answer gets typed
    for i, m in enumerate(messages):
        if m["role"] == "user":
            user_bubble(m["content"])
        else:
            k = f"{chat_id}-{i}"
            render_answer(m.get("response") or {"explanation": m["content"]}, key=k, animate=(k == animate_key))

    chat_full = questions_asked >= MAX_TURNS
    if chat_full:
        st.info(f"This chat has reached its {MAX_TURNS}-question limit. Start a new chat to continue.")

    # A clicked suggestion is asked exactly like a typed question.
    question = st.chat_input("Ask bUlleTin...", disabled=chat_full) or st.session_state.pop("pending_question", None)

    # ============================================================
    # 3. Answer a question
    # ============================================================

    if question:
        admin = auth.admin_client()
        left, next_free = quota.questions_left(admin, user["id"])
        if left == 0:
            when = next_free.astimezone(sidebar.user_tz()).strftime("%d %b, %I:%M %p") if next_free else "later"
            st.warning(f"You've used your {quota.DAILY_LIMIT} questions for the last 24 hours. "
                       f"You can ask again from {when}.")
            st.stop()

        if chat_id is None:
            chat_id = store.create_chat()
            sidebar.open_chat(chat_id)
        history = history_for_agent(store.get_messages(chat_id))
        store.add_message(chat_id, "user", question)
        quota.record_question(admin, user["id"])
        user_bubble(question)

        with st.spinner("Thinking... forecasts can take up to half a minute."):
            try:
                response = run_agent(question, history)
            except Exception as e:  # never show a raw error to a business user
                print(f"ERROR in run_agent: {e}")
                response = {"route_decision": "error", "found": False, "confidence": "N/A",
                            "explanation": "Something went wrong answering that. Please try again."}

        store.add_message(chat_id, "assistant", response.get("explanation", ""), response)
        st.session_state["animate"] = f"{chat_id}-{len(store.get_messages(chat_id)) - 1}"
        st.rerun()

except Exception as e:
    # Supabase login tokens expire; if that happens, ask the user to log in again instead of crashing.
    if "jwt" in str(e).lower() or "token" in str(e).lower():
        auth.sign_out()
        st.session_state["flash"] = "Your session expired. Please log in again."
        st.rerun()
    raise
