"""
Settings dialog, opened from the gear in the sidebar footer.

  Answers    which view chart answers open in (saved to the user's account)
  Dashboard  placeholders until the dashboard exists
  Account    who is signed in, and log out
"""
import html

import streamlit as st

from services import auth

VIEW_LABELS = {"table": ":material/table: Table", "chart": ":material/bar_chart: Chart"}


def _section(title: str):
    st.markdown(f'<div class="settings-section">{html.escape(title)}</div>', unsafe_allow_html=True)


def _save_view():
    # A segmented control can be clicked off (None); fall back to the saved value.
    value = st.session_state.get("settings-view") or st.session_state.get(auth.DEFAULT_VIEW_KEY, "table")
    st.session_state["settings-view"] = value
    error = auth.save_settings(**{auth.DEFAULT_VIEW_KEY: value})
    st.session_state["settings-error"] = error


@st.dialog("Settings", width="medium")
def open_dialog(user: dict):
    _section("Answers")
    if "settings-view" not in st.session_state:
        st.session_state["settings-view"] = st.session_state.get(auth.DEFAULT_VIEW_KEY, "table")
    st.segmented_control("Open chart answers as", list(VIEW_LABELS), format_func=VIEW_LABELS.get,
                         key="settings-view", on_change=_save_view)
    st.caption("Every chart answer has a table and chart switch. This sets which one opens first.")
    error = st.session_state.pop("settings-error", None)
    if error:
        st.error(error)

    _section("Dashboard")
    st.toggle("Add to dashboard", value=False, disabled=True, key="settings-add-dashboard",
              help="Pin a chart answer to your dashboard.")
    st.toggle("Customise dashboard", value=False, disabled=True, key="settings-customise-dashboard",
              help="Reorder, resize or remove dashboard tiles.")
    st.markdown('<div class="soon">Coming with the dashboard.</div>', unsafe_allow_html=True)

    _section("Account")
    st.markdown(f'<div class="account-line">{html.escape(user["name"])}<br>'
                f'<span class="email">{html.escape(user["email"])}</span></div>', unsafe_allow_html=True)
    if st.button("Log out", icon=":material/logout:", key="settings-logout"):
        auth.sign_out()
        st.query_params.clear()
        st.rerun()
