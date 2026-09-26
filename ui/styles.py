"""
The one CSS block (everything the theme file in .streamlit/config.toml can't do).

Palette
  canvas     #1E293B  steel blue (chat background)
  sidebar    #0F172A  deeper navy
  white      #FFFFFF  user bubble, input bar, assistant text
  label      #94A3B8  small section labels (EXPLANATION, DETAILS)
  accent     #7DD3FC  sky blue: buttons, Actual line
  forecast   #FB923C  orange: forecast line
  green      #34D399  recommendation
"""
import streamlit as st

CANVAS, SIDEBAR, WHITE, LABEL, ACCENT, FORECAST, GREEN = "#1E293B", "#0F172A", "#FFFFFF", "#94A3B8", "#7DD3FC", "#FB923C", "#34D399"

CSS = f"""
<style>
/* Narrower reading column, like a chat app */
.block-container {{ max-width: 860px; padding-top: 2rem; padding-bottom: 7rem; }}

/* User question: white bubble, blue text, right-aligned */
.user-bubble {{
  background: {WHITE}; color: {CANVAS}; padding: 0.7rem 1rem; border-radius: 16px 16px 4px 16px;
  margin: 1.2rem 0 0.8rem auto; width: fit-content; max-width: 80%; font-size: 1rem; line-height: 1.5;
  white-space: pre-wrap; word-wrap: break-word;
}}

/* Small uppercase section labels inside an answer */
.section-label {{
  color: {LABEL}; font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase;
  margin: 1rem 0 0.25rem 0;
}}

/* Recommendation: green bar and soft green background */
.recommendation {{
  border-left: 3px solid {GREEN}; background: rgba(52,211,153,0.12); border-radius: 4px;
  padding: 0.5rem 0 0.5rem 0.9rem; margin: 0.4rem 0; color: {WHITE};
}}

/* Caveats under an answer */
.note {{ color: {LABEL}; font-size: 0.85rem; margin: 0.15rem 0; }}

/* Greeting on the empty screen */
.greeting {{ text-align: center; font-size: 2.3rem; font-weight: 500; margin-top: 22vh; color: {WHITE}; }}
.greeting-sub {{ text-align: center; color: {LABEL}; margin-top: 0.4rem; }}

/* Input bar: solid white with blue text */
[data-testid="stChatInput"] {{ background: {WHITE}; border-radius: 14px; }}
[data-testid="stChatInput"] > div {{ background: {WHITE}; border-color: {WHITE}; }}
[data-testid="stChatInput"] textarea {{ color: {CANVAS} !important; caret-color: {CANVAS}; }}
[data-testid="stChatInput"] textarea::placeholder {{ color: #64748B !important; }}
[data-testid="stChatInput"] button {{ color: {CANVAS}; }}

/* Login card */
.login-title {{ text-align: center; font-size: 2.1rem; font-weight: 600; margin-top: 10vh; color: {WHITE}; }}
.login-sub {{ text-align: center; color: {LABEL}; margin: 0.3rem 0 1.6rem 0; }}

/* Sidebar: signed-in user */
.sidebar-user {{ color: {LABEL}; font-size: 0.85rem; margin-bottom: 0.4rem; }}

/* Primary buttons: white with blue text */
.stButton > button[kind="primary"] {{ background: {WHITE}; color: {CANVAS}; border: none; }}
</style>
"""


def apply():
    st.markdown(CSS, unsafe_allow_html=True)
