"""
The one CSS block: everything .streamlit/config.toml can't do.

Colours, radius, borders, fonts and the dataframe header live in config.toml (sturdier than CSS).
This file styles only our own HTML pieces and a few Streamlit parts that have no config option.

Palette
  ink       #0A1120  sidebar
  canvas    #0D1628  chat background
  surface   #15213A  inputs, cards
  raised    #1A2844  user bubble
  line      #22314D  hairlines and borders
  text      #E6ECF5  main text
  muted     #8C9AB0  labels, captions, notes
  accent    #7DD3FC  sky: focus, links, Actual series, the U and T of the wordmark
  forecast  #FB923C  orange: forecast line and band
  green     #34D399  mint: recommendation
"""
import streamlit as st

INK, CANVAS, SURFACE, RAISED, LINE = "#0A1120", "#0D1628", "#15213A", "#1A2844", "#22314D"
TEXT, MUTED, ACCENT, FORECAST, GREEN = "#E6ECF5", "#8C9AB0", "#7DD3FC", "#FB923C", "#34D399"
# Older names, kept so any other import still works.
SIDEBAR, WHITE, LABEL = INK, TEXT, MUTED

# Vega-Lite theme for Ask bUlleTin charts. The spec from agent/charts.py carries the data and the
# series colours; this block only styles text, axes and grid to match the canvas.
VEGA_CONFIG = {
    "font": "Inter, sans-serif",
    "padding": {"left": 4, "right": 12, "top": 8, "bottom": 4},
    "title": {"color": "#C3CDDC", "fontSize": 13, "fontWeight": 500, "anchor": "start", "offset": 14},
    "axis": {"labelColor": MUTED, "titleColor": MUTED, "labelFontSize": 11, "titleFontSize": 11,
             "titleFontWeight": 500, "labelPadding": 6, "titlePadding": 10,
             "domainColor": LINE, "tickColor": LINE, "gridColor": "rgba(148,163,184,0.12)"},
    "axisX": {"grid": False, "tickSize": 4},
    "axisY": {"domain": False, "ticks": False, "gridDash": [2, 3]},
    "legend": {"labelColor": "#C3CDDC", "labelFontSize": 11, "symbolType": "circle", "symbolSize": 70,
               "padding": 8},
    "view": {"stroke": None},
}

CSS = f"""
<style>
/* ---------- Base ---------- */
html, body, [class*="st-"] {{ -webkit-font-smoothing: antialiased; font-feature-settings: "cv11", "ss01"; }}
.block-container {{ max-width: 780px; padding-top: 2.5rem; padding-bottom: 8rem; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {{ line-height: 1.65; }}
[data-testid="stMarkdownContainer"] strong {{ font-weight: 600; color: {TEXT}; }}
.sr-only {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden;
            clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }}
button:focus-visible, [role="tab"]:focus-visible {{ outline: 2px solid {ACCENT}; outline-offset: 2px; }}

/* ---------- Chat ---------- */
.user-bubble {{
  background: {RAISED}; color: {TEXT}; border: 1px solid {LINE};
  padding: 0.65rem 1rem; border-radius: 18px 18px 6px 18px;
  margin: 2.2rem 0 1rem auto; width: fit-content; max-width: 78%;
  line-height: 1.55; white-space: pre-wrap; word-wrap: break-word;
}}
.section-label {{ color: {MUTED}; font-size: 0.8rem; font-weight: 500; margin: 1.1rem 0 0.3rem 0; }}
.note {{ color: {MUTED}; font-size: 0.86rem; line-height: 1.5; margin: 0.45rem 0;
         padding-left: 0.75rem; border-left: 2px solid {LINE}; }}
.recommendation {{
  background: rgba(52,211,153,0.07); border: 1px solid rgba(52,211,153,0.22); border-radius: 12px;
  padding: 0.75rem 1rem 0.8rem; margin: 0.4rem 0 0.6rem; color: {TEXT}; line-height: 1.55;
}}
.recommendation .rec-label {{ color: {GREEN}; font-size: 0.78rem; font-weight: 600; margin-bottom: 0.2rem; }}

/* Table / chart switch and the chart card */
[class*="st-key-visual-"] [data-testid="stButtonGroup"] button {{ min-height: 30px; padding: 0.15rem 0.65rem; }}
[data-testid="stVegaLiteChart"] {{
  background: rgba(21,33,58,0.55); border: 1px solid {LINE}; border-radius: 12px; padding: 0.6rem 0.4rem 0.2rem;
}}
[data-testid="stDataFrame"] {{ border-radius: 10px; }}

/* Details: a quiet hairline disclosure instead of a boxed panel */
[data-testid="stExpander"] details {{ border: none; border-top: 1px solid {LINE}; border-radius: 0; background: transparent; }}
[data-testid="stExpander"] summary {{ padding-left: 0; padding-right: 0; color: {MUTED}; font-size: 0.88rem; }}
[data-testid="stExpander"] summary:hover {{ color: {TEXT}; }}
[data-testid="stExpanderDetails"] {{ padding-left: 0; padding-right: 0; }}

/* ---------- Input bar ---------- */
[data-testid="stChatInput"] {{
  background: {SURFACE}; border: 1px solid {LINE}; border-radius: 16px;
  box-shadow: 0 10px 30px rgba(2,6,23,0.45); transition: border-color 120ms ease, box-shadow 120ms ease;
}}
[data-testid="stChatInput"]:focus-within {{
  border-color: rgba(125,211,252,0.55); box-shadow: 0 0 0 3px rgba(125,211,252,0.12), 0 10px 30px rgba(2,6,23,0.45);
}}
[data-testid="stChatInput"] > div {{ background: transparent; border: none; }}
[data-testid="stChatInput"] textarea {{ color: {TEXT} !important; caret-color: {ACCENT}; }}
[data-testid="stChatInput"] textarea::placeholder {{ color: {MUTED} !important; }}
[data-testid="stChatInputSubmitButton"]:not(:disabled) {{ background: {ACCENT}; color: {CANVAS}; border-radius: 10px; }}

/* ---------- Empty state ---------- */
.greeting {{ text-align: center; font-size: 2rem; font-weight: 600; letter-spacing: -0.025em;
             margin-top: 18vh; color: {TEXT}; }}
.greeting-sub {{ text-align: center; color: {MUTED}; margin: 0.4rem 0 2rem; }}
.st-key-suggestions button {{
  justify-content: flex-start; text-align: left; min-height: 3.1rem; padding: 0.6rem 0.9rem;
  background: {SURFACE}; border: 1px solid {LINE}; color: #C3CDDC; font-weight: 400;
  transition: border-color 120ms ease, color 120ms ease;
}}
.st-key-suggestions button:hover {{ border-color: rgba(125,211,252,0.45); color: {TEXT}; }}
/* The one entrance: greeting and suggestions rise in once, on an empty chat */
.greeting, .greeting-sub, .st-key-suggestions {{ animation: rise 420ms cubic-bezier(.2,.7,.2,1) both; }}
.greeting-sub {{ animation-delay: 60ms; }}
.st-key-suggestions {{ animation-delay: 120ms; }}
@keyframes rise {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
@media (prefers-reduced-motion: reduce) {{
  .greeting, .greeting-sub, .st-key-suggestions {{ animation: none; }}
  * {{ transition: none !important; }}
}}

/* ---------- Sidebar ---------- */
.brand {{ font-size: 1.25rem; font-weight: 650; letter-spacing: -0.02em; color: {TEXT}; line-height: 1.2; }}
.brand [aria-hidden] > span {{ color: {ACCENT}; }}
.brand-sub {{ color: {MUTED}; font-size: 0.8rem; margin: 0.15rem 0 1.1rem; }}
.st-key-newchat button {{ justify-content: flex-start; background: {RAISED}; border: 1px solid {LINE}; font-weight: 500; }}
.st-key-newchat button:hover {{ border-color: rgba(125,211,252,0.45); }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
  color: {MUTED}; font-size: 0.75rem; font-weight: 500; margin: 0.9rem 0 0.3rem 0.55rem;
}}

[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] {{ gap: 0.4rem; }}
[class*="st-key-chatrow-"] [data-testid="stPopover"] button div[aria-hidden="true"] {{ display: none; }}

/* Chat rows: left-aligned, borderless, highlighted when open, menu on hover */
[class*="st-key-chatrow-"] [data-testid="stHorizontalBlock"] {{ gap: 0.15rem; }}
[class*="st-key-chatrow-"] [data-testid="stColumn"]:first-child button {{
  justify-content: flex-start; width: 100%; padding: 0.4rem 0.55rem; border-radius: 8px;
  color: #C3CDDC; font-weight: 400; transition: background 120ms ease, color 120ms ease;
}}
[class*="st-key-chatrow-"] [data-testid="stColumn"]:first-child button > div,
.st-key-newchat button > div, .st-key-suggestions button > div, .st-key-sidebar-footer button > div {{
  justify-content: flex-start; width: 100%; min-width: 0;
}}
[class*="st-key-chatrow-"] [data-testid="stColumn"]:first-child button p {{
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left;
}}
[class*="st-key-chatrow-"] [data-testid="stColumn"]:first-child button:hover {{ background: rgba(148,163,184,0.08); color: {TEXT}; }}
[class*="st-key-chatrow-active"] [data-testid="stColumn"]:first-child button {{
  background: rgba(125,211,252,0.10); color: {TEXT};
}}
[class*="st-key-chatrow-"] [data-testid="stPopover"] button {{
  border: none; background: transparent; color: {MUTED}; min-height: 30px; padding: 0 0.3rem;
}}
@media (hover: hover) {{
  [class*="st-key-chatrow-"] [data-testid="stPopover"] button {{ opacity: 0; transition: opacity 120ms ease; }}
  [class*="st-key-chatrow-"]:hover [data-testid="stPopover"] button,
  [class*="st-key-chatrow-"] [data-testid="stPopover"] button:focus-visible,
  [class*="st-key-chatrow-active"] [data-testid="stPopover"] button {{ opacity: 1; }}
}}

/* Account footer */
.st-key-sidebar-footer {{ border-top: 1px solid {LINE}; padding-top: 0.8rem; margin-top: 1rem; }}
.account {{ display: flex; align-items: center; gap: 0.6rem; color: {TEXT}; font-size: 0.9rem; margin-bottom: 0.4rem; }}
.account .avatar {{
  width: 28px; height: 28px; border-radius: 50%; display: inline-grid; place-items: center;
  background: rgba(125,211,252,0.14); color: {ACCENT}; font-size: 0.8rem; font-weight: 600;
}}
.account .email {{ color: {MUTED}; font-size: 0.78rem; }}
.st-key-sidebar-footer button {{ justify-content: flex-start; color: #C3CDDC; font-weight: 400; }}

/* ---------- Settings dialog ---------- */
div[role="dialog"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 16px; }}
.settings-section {{ color: {TEXT}; font-size: 0.92rem; font-weight: 600; margin: 1.2rem 0 0.4rem; }}
.settings-section:first-child {{ margin-top: 0.2rem; }}
.soon {{ color: {MUTED}; font-size: 0.8rem; margin: -0.2rem 0 0.6rem; }}
.account-line {{ color: {TEXT}; line-height: 1.5; margin-bottom: 0.6rem; }}
.account-line .email {{ color: {MUTED}; font-size: 0.85rem; }}

/* ---------- Login ---------- */
.login-title {{ text-align: center; font-size: 2.2rem; font-weight: 650; letter-spacing: -0.03em;
                margin-top: 11vh; color: {TEXT}; }}
.login-title [aria-hidden] > span {{ color: {ACCENT}; }}
.login-sub {{ text-align: center; color: {MUTED}; margin: 0.35rem 0 1.8rem 0; }}
[data-testid="stForm"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 14px; padding: 1.2rem 1.2rem 0.8rem; }}

/* Primary buttons: sky with dark text (Log in, Create account, Save) */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
  background: {ACCENT}; border-color: {ACCENT}; color: {CANVAS}; font-weight: 600;
}}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
  background: #A5E1FD; border-color: #A5E1FD; color: {CANVAS};
}}
</style>
"""


def apply():
    st.markdown(CSS, unsafe_allow_html=True)
