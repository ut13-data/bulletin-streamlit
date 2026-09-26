"""
Login, registration and the two Supabase connections.

  user client   one per browser session, kept in st.session_state. It carries
                the logged-in user's token, so Row Level Security only lets it
                see that user's chats.
  admin client  uses the service key and bypasses Row Level Security. Used ONLY
                for the usage table (the daily question limit), which users must
                not be able to read or change. Safe to share (st.cache_resource)
                because it holds no user session.

Never put the user client in st.cache_resource: that cache is shared by every
visitor, so one person's login would leak to everyone.
"""
import streamlit as st
from supabase import Client, create_client

from agent.config import get_secret


def user_client() -> Client:
    if "sb_client" not in st.session_state:
        st.session_state["sb_client"] = create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_ANON_KEY"))
    return st.session_state["sb_client"]


@st.cache_resource
def admin_client() -> Client:
    return create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_SERVICE_KEY"))


def current_user() -> dict | None:
    """{"id", "email", "name"} when logged in, else None."""
    return st.session_state.get("user")


def _remember(user) -> dict:
    meta = user.user_metadata or {}
    info = {"id": user.id, "email": user.email, "name": meta.get("name") or user.email.split("@")[0]}
    st.session_state["user"] = info
    return info


def _friendly(error: Exception) -> str:
    msg = str(error).lower()
    if "invalid login credentials" in msg:
        return "Wrong email or password."
    if "already registered" in msg or "already been registered" in msg:
        return "An account with this email already exists. Please log in."
    if "password" in msg and ("6" in msg or "short" in msg or "weak" in msg):
        return "Please choose a password with at least 6 characters."
    if "rate limit" in msg or "too many" in msg:
        return "Too many attempts. Please wait a minute and try again."
    if "email" in msg and "invalid" in msg:
        return "Please enter a valid email address."
    return "Something went wrong. Please try again."


def sign_up(name: str, email: str, password: str) -> str | None:
    """Returns an error message, or None on success (user is then logged in)."""
    try:
        res = user_client().auth.sign_up({"email": email.strip(), "password": password,
                                          "options": {"data": {"name": name.strip()}}})
    except Exception as e:
        return _friendly(e)
    if res.session is None:
        # Email confirmation is switched on in Supabase: no session until they confirm.
        return "Account created. Please confirm your email, then log in."
    _remember(res.user)
    return None


def sign_in(email: str, password: str) -> str | None:
    try:
        res = user_client().auth.sign_in_with_password({"email": email.strip(), "password": password})
    except Exception as e:
        return _friendly(e)
    _remember(res.user)
    return None


def sign_out():
    try:
        user_client().auth.sign_out()
    except Exception:
        pass
    for key in ("user", "sb_client", "current_chat", "animate"):
        st.session_state.pop(key, None)
