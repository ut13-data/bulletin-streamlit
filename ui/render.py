"""
Draws one answer: explanation, chart, notes, recommendation, and a collapsed Details section.
Charts use Altair so labels keep the exact order the agent sends (months, FY24, ...).
"""
import html
import time

import altair as alt
import pandas as pd
import streamlit as st

from ui.styles import ACCENT, FORECAST, LABEL

SERIES_COLORS = {"Actual": ACCENT, "Forecast": FORECAST, "Current": LABEL, "Scenario": ACCENT}
OTHER_COLORS = [ACCENT, FORECAST, "#A78BFA", "#34D399", "#F472B6"]
BAND = ("Likely low", "Likely high")


def label(text: str):
    st.markdown(f'<div class="section-label">{html.escape(text)}</div>', unsafe_allow_html=True)


def user_bubble(text: str):
    st.markdown(f'<div class="user-bubble">{html.escape(text)}</div>', unsafe_allow_html=True)


# ============================================================
# Charts
# ============================================================

def _scale(chart: dict) -> tuple[float, str]:
    """Rupee charts are shown in lakh or crore so the axis stays readable."""
    values = [abs(v) for s in chart["series"] for v in s["values"] if v is not None]
    peak = max(values) if values else 0
    unit = chart.get("unit")
    if unit == "inr":
        if peak >= 1e7:
            return 1e7, "₹ Crore"
        if peak >= 1e5:
            return 1e5, "₹ Lakh"
        return 1, "₹"
    return 1, {"pct": "%", "ratio": "times per year", "days": "days"}.get(unit, "")


def _long_frame(chart: dict, divisor: float) -> pd.DataFrame:
    rows = []
    for s in chart["series"]:
        for i, (x, v) in enumerate(zip(chart["x_axis_data"], s["values"])):
            if v is not None:
                rows.append({"x": str(x), "order": i, "series": s["name"], "value": v / divisor})
    return pd.DataFrame(rows)


def _axis():
    return {"labelColor": "#CBD5E1", "titleColor": LABEL, "gridColor": "rgba(148,163,184,0.18)",
            "domainColor": "rgba(148,163,184,0.3)", "tickColor": "rgba(148,163,184,0.3)"}


def render_chart(chart: dict):
    if not chart or not chart.get("series") or not chart.get("x_axis_data"):
        return
    divisor, unit_title = _scale(chart)
    df = _long_frame(chart, divisor)
    if df.empty:
        return
    order = [str(x) for x in chart["x_axis_data"]]
    names = [s["name"] for s in chart["series"] if s["name"] not in BAND]
    colors = [SERIES_COLORS.get(n, OTHER_COLORS[i % len(OTHER_COLORS)]) for i, n in enumerate(names)]
    color = alt.Color("series:N", scale=alt.Scale(domain=names, range=colors),
                      legend=alt.Legend(title=None, orient="bottom", labelColor="#E2E8F0"))
    tooltip = [alt.Tooltip("x:N", title="Item"), alt.Tooltip("series:N", title="Measure"),
               alt.Tooltip("value:Q", title=unit_title or "value", format=",.2f")]

    if chart.get("style") == "bar":
        many_long_labels = len(order) > 6 or max(len(x) for x in order) > 12
        if len(names) == 1 and many_long_labels:
            # Horizontal bars: long product names stay readable.
            layer = alt.Chart(df).mark_bar(cornerRadiusEnd=3, color=colors[0]).encode(
                y=alt.Y("x:N", sort=order, title=None, axis=alt.Axis(labelLimit=260)),
                x=alt.X("value:Q", title=unit_title), tooltip=tooltip)
            height = max(180, 28 * len(order))
        else:
            layer = alt.Chart(df).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                x=alt.X("x:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
                xOffset=alt.XOffset("series:N", sort=names),
                y=alt.Y("value:Q", title=unit_title), color=color, tooltip=tooltip)
            height = 300
    else:
        base_x = alt.X("x:N", sort=order, title=None, axis=alt.Axis(labelAngle=-45 if len(order) > 12 else 0))
        lines_df = df[~df.series.isin(BAND)]
        layer = alt.Chart(lines_df).mark_line(point=alt.OverlayMarkDef(size=28), strokeWidth=2.5).encode(
            x=base_x, y=alt.Y("value:Q", title=unit_title, scale=alt.Scale(zero=False)), color=color,
            strokeDash=alt.StrokeDash("series:N", legend=None, scale=alt.Scale(
                domain=names, range=[[6, 4] if n == "Forecast" else [1, 0] for n in names])),
            tooltip=tooltip)
        band = df[df.series.isin(BAND)].pivot_table(index=["x", "order"], columns="series", values="value").reset_index()
        if set(BAND) <= set(band.columns):
            area = alt.Chart(band).mark_area(opacity=0.18, color=FORECAST).encode(
                x=base_x, y=alt.Y(f"{BAND[0]}:Q"), y2=alt.Y2(f"{BAND[1]}:Q"))
            layer = area + layer
        height = 320

    final = (layer.properties(height=height, title=alt.TitleParams(chart.get("title", ""), anchor="start",
                                                                    color=LABEL, fontSize=12, fontWeight="normal"))
             .configure_axis(**_axis()).configure_view(strokeWidth=0).configure(background="transparent"))
    st.altair_chart(final, width="stretch", theme=None)


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
    label("Answer" if r.get("route_decision") in ("metric", "adhoc") else "Reply")
    if animate:
        st.write_stream(_typewriter(explanation))
    else:
        st.markdown(explanation)

    if r.get("chart"):
        render_chart(r["chart"])

    for note in r.get("notes") or []:
        st.markdown(f'<div class="note">{html.escape(note)}</div>', unsafe_allow_html=True)

    if r.get("recommendation"):
        label("Recommendation")
        st.markdown(f'<div class="recommendation">{html.escape(r["recommendation"])}</div>', unsafe_allow_html=True)

    has_details = any(r.get(k) for k in ("confidence", "definitions", "table", "sql", "sources"))
    if has_details and r.get("confidence") != "N/A":
        with st.expander("Details"):
            if r.get("confidence"):
                label("AI confidence")
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
