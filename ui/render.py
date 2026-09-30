"""
Draws one answer: explanation, visual (table or chart), notes, recommendation, and a collapsed Details section.

The visual comes ready-made from agent/charts.py:
  chart_spec   Vega-Lite spec (data + encoding). This file only adds the dark theme.
  chart_table  the same numbers as a wide table.
So this file never decides a chart type. Old saved answers (only a `chart` dict) are rebuilt
with spec_from_legacy, which goes through the same code path.
"""
import html
import time

import pandas as pd
import streamlit as st

from agent.charts import spec_from_legacy
from services.auth import DEFAULT_VIEW_KEY
from ui.styles import VEGA_CONFIG

VIEWS = {"table": ":material/table:", "chart": ":material/bar_chart:"}


def label(text: str):
    st.markdown(f'<div class="section-label">{html.escape(text)}</div>', unsafe_allow_html=True)


def user_bubble(text: str):
    st.markdown(f'<div class="user-bubble">{html.escape(text)}</div>', unsafe_allow_html=True)


# ============================================================
# Visual: table view or chart view
# ============================================================

def visual_of(r: dict) -> tuple[dict | None, dict | None]:
    """(chart_spec, chart_table) for an answer; old saved answers are converted on the fly."""
    if r.get("chart_spec") and r.get("chart_table"):
        return r["chart_spec"], r["chart_table"]
    return spec_from_legacy(r.get("chart"))


def inr_text(v) -> str:
    """Whole rupees with Indian grouping: 2072505 -> ₹20,72,505 (same on every browser)."""
    if v is None or pd.isna(v):
        return ""
    n = int(round(float(v)))
    digits = str(abs(n))
    if len(digits) > 3:
        head, groups = digits[:-3], [digits[-3:]]
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join([head] + groups if head else groups)
    return f"{'-' if n < 0 else ''}₹{digits}"


FORMATTERS = {
    "inr": inr_text,
    "pct": lambda v: "" if pd.isna(v) else f"{v:.1f}%",
    "number": lambda v: "" if pd.isna(v) else f"{v:,.2f}".rstrip("0").rstrip("."),
}


def _forecast_display(table: dict) -> dict:
    """
    Month | Actual | Forecast | Likely low | Likely high has empty cells by design (no forecast for past
    months), and st.dataframe always prints "None" in empty number cells. For display only, fold it into
    Month | Type | Value | Likely range, which has no gaps. chart_table itself is unchanged.
    """
    fmt = next(c["format"] for c in table["columns"] if c["key"] == "Actual")
    to_text = FORMATTERS.get(fmt, FORMATTERS["number"])
    rows = []
    for r in table["rows"]:
        is_fc = r.get("Actual") is None
        low, high = r.get("Likely low"), r.get("Likely high")
        rows.append({"x": r["x"], "type": "Forecast" if is_fc else "Actual",
                     "value": r.get("Forecast") if is_fc else r["Actual"],
                     "range": f"{to_text(low)} to {to_text(high)}" if low is not None and high is not None else ""})
    columns = [table["columns"][0], {"key": "type", "label": "Type", "format": "text"},
               {"key": "value", "label": "Value", "format": fmt},
               {"key": "range", "label": "Likely range", "format": "text"}]
    return {"columns": columns, "rows": rows}


def table_frame(table: dict):
    """
    Wide table -> pandas Styler + column_config.
    The Styler only changes what is DISPLAYED (Indian grouping); the numbers underneath stay
    numbers, so clicking a column header still sorts correctly.
    """
    if {"Actual", "Forecast"} <= {c["key"] for c in table["columns"]}:
        table = _forecast_display(table)
    cols = table["columns"]
    df = pd.DataFrame(table["rows"], columns=[c["key"] for c in cols])
    formats = {}
    for c in cols:
        if c["format"] == "text":
            continue
        fmt = FORMATTERS.get(c["format"], FORMATTERS["number"])
        df[c["key"]] = pd.to_numeric(df[c["key"]])
        if df[c["key"]].isna().any():
            df[c["key"]] = df[c["key"]].map(fmt)     # a column with gaps shows blanks (sorts as text)
        else:
            formats[c["key"]] = fmt
    config = {c["key"]: st.column_config.Column(c["label"]) for c in cols}
    return df.style.format(formats), config


def render_chart(spec: dict, key: str):
    themed = {**spec, "config": VEGA_CONFIG}          # copy: never change the saved response
    st.vega_lite_chart(themed, theme=None, width="stretch", key=f"chart-{key}")


def render_table(table: dict, key: str):
    df, config = table_frame(table)
    st.dataframe(df, column_config=config, hide_index=True, width="stretch", key=f"vtbl-{key}")


def render_visual(r: dict, key: str):
    spec, table = visual_of(r)
    if not spec or not table:
        return
    default = st.session_state.get(DEFAULT_VIEW_KEY, "table")
    state_key = f"view-{key}"
    if state_key not in st.session_state:            # set once, so each message keeps its own view
        st.session_state[state_key] = default
    with st.container(key=f"visual-{key}"):          # key becomes a CSS class for styles.py
        view = st.segmented_control("View", list(VIEWS), format_func=VIEWS.get, key=state_key,
                                    label_visibility="collapsed") or default   # None if clicked off
        if view == "chart":
            render_chart(spec, key)
        else:
            render_table(table, key)


# ============================================================
# One full answer
# ============================================================

def _typewriter(text: str):
    """Yields the text a word at a time so it appears to be typed."""
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.02)   # smaller = faster


def render_answer(r: dict, key: str, animate: bool = False):
    explanation = r.get("explanation") or ""
    if animate:
        st.write_stream(_typewriter(explanation))
    else:
        st.markdown(explanation)

    render_visual(r, key)

    for note in r.get("notes") or []:
        st.markdown(f'<div class="note">{html.escape(note)}</div>', unsafe_allow_html=True)

    if r.get("recommendation"):
        st.markdown(f'<div class="recommendation"><div class="rec-label">Recommendation</div>'
                    f'{html.escape(r["recommendation"])}</div>', unsafe_allow_html=True)

    has_details = any(r.get(k) for k in ("confidence", "definitions", "table", "sql", "sources"))
    if has_details and r.get("confidence") != "N/A":
        with st.expander("Details"):
            if r.get("confidence"):
                label("Confidence")
                st.markdown(r["confidence"])
            if r.get("table"):
                label("Numbers")
                st.dataframe(pd.DataFrame(r["table"]), hide_index=True, width="stretch", key=f"tbl-{key}")
            if r.get("definitions"):
                label("How it was calculated")
                for d in r["definitions"]:
                    st.markdown(f"- {d}")
            if r.get("sources"):
                label("Evidence")
                for s in r["sources"]:
                    st.markdown(f"- {s.get('document')}: {s.get('subsection') or s.get('section')}")
            if r.get("sql"):
                label("SQL that ran")
                for q in r["sql"]:
                    st.code(q.strip(), language="sql")
            if r.get("data_through"):
                st.caption(f"Data available: {r['data_through']}")
