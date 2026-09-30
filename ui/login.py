"""Log in / create account screen, shown until the user is signed in."""
import streamlit as st

from services import auth


def render():
    st.markdown('<div class="login-title"><span class="sr-only">bUlleTin</span><span aria-hidden="true">b<span>U</span>lle<span>T</span>in</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="login-sub">Ask Balaji Pharma\'s data anything.</div>', unsafe_allow_html=True)

    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        flash = st.session_state.pop("flash", None)
        if flash:
            st.warning(flash)
        log_in, register = st.tabs(["Log in", "Create account"])

        with log_in:
            with st.form("login"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Log in", type="primary", width="stretch"):
                    if not email or not password:
                        st.error("Please enter your email and password.")
                    else:
                        error = auth.sign_in(email, password)
                        if error:
                            st.error(error)
                        else:
                            st.rerun()

        with register:
            with st.form("register"):
                name = st.text_input("Your name")
                email = st.text_input("Email", key="reg_email")
                password = st.text_input("Password (at least 6 characters)", type="password", key="reg_pw")
                if st.form_submit_button("Create account", type="primary", width="stretch"):
                    if not name.strip() or not email or len(password) < 6:
                        st.error("Please fill in your name, email and a password of at least 6 characters.")
                    else:
                        error = auth.sign_up(name, email, password)
                        if error:
                            st.info(error) if error.startswith("Account created") else st.error(error)
                        else:
                            st.rerun()
