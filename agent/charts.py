"""
The ONE place that decides how an answer is drawn.

Input : a tidy long DataFrame with columns x, order, series, value
        (one row per point; `order` keeps months / periods in the right order),
        plus the chart kind, the unit and a title.
Output: chart_spec   a Vega-Lite v6 spec (data + encoding, transparent background, no theme)
        chart_table  the same numbers as a wide, sortable table for the table view

Both outputs are built from the same DataFrame, so the chart and the table can never disagree.
Front ends only merge in their own theme config. They never decide the chart type.

Chart types (one rule, in choose_mark):
  trend      -> line
  forecast   -> Actual line + dashed Forecast line + Likely low/high band, joined at the last actual month
  breakdown  -> sorted bar, horizontal when labels are long or there are more than 6
  compare    -> grouped bar
  scenario   -> grouped bar
"""
import math

import pandas as pd

VL_SCHEMA = "https://vega.github.io/schema/vega-lite/v6.json"
KINDS = ("trend", "forecast", "breakdown", "compare", "scenario")

# Semantic series colours live in the spec (same meaning in every app). Everything else is theme.
ACTUAL, FORECAST, NEUTRAL = "#7DD3FC", "#FB923C", "#94A3B8"
SERIES_COLORS = {"Actual": ACTUAL, "Forecast": FORECAST, "Current": NEUTRAL, "Scenario": ACTUAL}
OTHER_COLORS = [ACTUAL, FORECAST, "#A78BFA", "#34D399", "#F472B6"]
BAND = ("Likely low", "Likely high")

UNIT_TITLES = {"pct": "%", "ratio": "times per year", "days": "days"}
TABLE_FORMATS = {"inr": "inr", "pct": "pct"}          # anything else -> "number"
X_LABELS = {"trend": "Period", "forecast": "Month", "compare": "Period",
            "breakdown": "Item", "scenario": "Metric"}


# ============================================================
# Input helpers
# ============================================================

def _num(v) -> float | None:
    """Plain float, or None for missing / NaN / non-numbers."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def long_frame(x: list, series: dict[str, list]) -> pd.DataFrame:
    """Turn x labels + {series name: values} into the tidy long frame. Missing values are dropped."""
    rows = []
    for name, values in series.items():
        for i, (label, v) in enumerate(zip(x, values)):
            v = _num(v)
            if v is not None:
                rows.append({"x": str(label), "order": i, "series": str(name), "value": v})
    return pd.DataFrame(rows, columns=["x", "order", "series", "value"])


def scale(values, unit: str | None) -> tuple[float, str]:
    """Rupee charts are shown in lakh or crore so the axis stays readable. Returns (divisor, axis title)."""
    peak = max((abs(v) for v in values), default=0)
    if unit == "inr":
        if peak >= 1e7:
            return 1e7, "₹ Crore"
        if peak >= 1e5:
            return 1e5, "₹ Lakh"
        return 1.0, "₹"
    return 1.0, UNIT_TITLES.get(unit or "", "")


def choose_mark(kind: str, labels: list[str], n_series: int) -> str:
    """The single rule that picks the chart type."""
    if kind == "forecast":
        return "forecast"
    if kind == "trend":
        return "line"
    long_labels = len(labels) > 6 or max((len(s) for s in labels), default=0) > 12
    if kind == "breakdown" and n_series == 1 and long_labels:
        return "bar_horizontal"
    return "bar"


# ============================================================
# Spec pieces
# ============================================================

def _colors(names: list[str]) -> list[str]:
    return [SERIES_COLORS.get(n, OTHER_COLORS[i % len(OTHER_COLORS)]) for i, n in enumerate(names)]


def _color(names: list[str]) -> dict:
    legend = {"title": None, "orient": "bottom"} if len(names) > 1 else None
    return {"field": "series", "type": "nominal",
            "scale": {"domain": names, "range": _colors(names)}, "legend": legend}


def _tooltip(x_label: str, unit_title: str) -> list[dict]:
    return [{"field": "x", "type": "nominal", "title": x_label},
            {"field": "series", "type": "nominal", "title": "Measure"},
            {"field": "value", "type": "quantitative", "title": unit_title or "Value", "format": ",.2f"}]


def _with_join(df: pd.DataFrame) -> pd.DataFrame:
    """Forecast only: copy the last actual point into every forecast series so the lines connect."""
    df = df.assign(join=False)
    actual = df[df.series == "Actual"]
    future = [s for s in dict.fromkeys(df.series) if s != "Actual"]
    if actual.empty or not future:
        return df
    last = actual.loc[actual.order.idxmax()]
    add = [{"x": last.x, "order": int(last.order), "series": s, "value": float(last.value), "join": True}
           for s in future if not ((df.series == s) & (df.order == last.order)).any()]
    return pd.concat([df, pd.DataFrame(add)], ignore_index=True) if add else df


def _line_layer(names, x_enc, y_enc, tooltip, dashed: bool) -> dict:
    enc = {"x": x_enc, "y": y_enc, "color": _color(names), "tooltip": tooltip}
    if dashed:
        enc["strokeDash"] = {"field": "series", "type": "nominal", "legend": None,
                             "scale": {"domain": names,
                                       "range": [[6, 4] if n == "Forecast" else [1, 0] for n in names]}}
    return {"mark": {"type": "line", "point": {"size": 28}, "strokeWidth": 2.5}, "encoding": enc}


def _spec(df: pd.DataFrame, kind: str, title: str, x_label: str,
          divisor: float, unit_title: str, unit: str | None) -> dict:
    names_all = list(dict.fromkeys(df.series))
    names = [n for n in names_all if n not in BAND]
    order = list(dict.fromkeys(df.sort_values("order", kind="stable").x))
    mark = choose_mark(kind, order, len(names))
    tooltip = _tooltip(x_label, unit_title)
    axis_title = unit_title or None

    if mark == "forecast":
        df = _with_join(df)
    else:
        df = df.assign(join=False)
    # Raw rupees go in the data (exactly the table's numbers). Vega-Lite divides for the axis, so no
    # precision is lost: rounding already-scaled crore values to 4 decimals would round to Rs 1,000.
    values = [{"x": r.x, "order": int(r.order), "series": r.series,
               "raw": round(float(r.value), 4), "join": bool(r.join)} for r in df.itertuples()]
    scaled = {"calculate": f"datum.raw / {divisor:g}", "as": "value"}

    body: dict
    if mark in ("line", "forecast"):
        x_enc = {"field": "x", "type": "nominal", "sort": order, "title": None,
                 "axis": {"labelAngle": -45 if len(order) > 12 else 0}}
        y_enc = {"field": "value", "type": "quantitative", "title": axis_title, "scale": {"zero": False}}
        line = _line_layer(names, x_enc, y_enc, tooltip, dashed=(mark == "forecast"))
        has_band = set(BAND) <= set(names_all)
        if mark == "forecast":
            line["transform"] = [{"filter": {"not": {"field": "series", "oneOf": list(BAND)}}}]
        if mark == "forecast" and has_band:
            band = {"transform": [{"filter": {"field": "series", "oneOf": list(BAND)}},
                                  {"pivot": "series", "value": "value", "groupby": ["x", "order"]}],
                    "mark": {"type": "area", "opacity": 0.18, "color": FORECAST},
                    "encoding": {"x": x_enc,
                                 "y": {"field": BAND[0], "type": "quantitative", "title": axis_title},
                                 "y2": {"field": BAND[1]}}}
            body = {"layer": [band, line]}
        else:
            body = line
        height = 320
    elif mark == "bar_horizontal":
        body = {"mark": {"type": "bar", "cornerRadiusEnd": 3, "color": _colors(names)[0]},
                "encoding": {"y": {"field": "x", "type": "nominal", "sort": order, "title": None,
                                   "axis": {"labelLimit": 260}},
                             "x": {"field": "value", "type": "quantitative", "title": axis_title},
                             "tooltip": tooltip}}
        height = max(180, 28 * len(order))
    else:  # grouped (or single) vertical bar
        enc = {"x": {"field": "x", "type": "nominal", "sort": order, "title": None, "axis": {"labelAngle": 0}},
               "y": {"field": "value", "type": "quantitative", "title": axis_title},
               "color": _color(names), "tooltip": tooltip}
        if len(names) > 1:
            enc["xOffset"] = {"field": "series", "type": "nominal", "sort": names}
        body = {"mark": {"type": "bar", "cornerRadiusTopLeft": 3, "cornerRadiusTopRight": 3}, "encoding": enc}
        height = 300

    return {
        "$schema": VL_SCHEMA,
        "title": {"text": title, "anchor": "start"},
        "width": "container",
        "height": height,
        "background": "transparent",
        "data": {"values": values},
        **body,
        "transform": [scaled] + body.get("transform", []),
        # Not drawn. Lets front ends and tests know how the numbers were scaled.
        "usermeta": {"bulletin": {"kind": kind, "mark": mark, "unit": unit,
                                  "divisor": divisor, "unit_title": unit_title}},
    }


def _table(df: pd.DataFrame, unit: str | None, x_label: str) -> dict:
    """Wide table: one row per x, one column per series. Raw numbers, formatted by the front end."""
    names = list(dict.fromkeys(df.series))
    fmt = TABLE_FORMATS.get(unit or "", "number")
    rows: dict[int, dict] = {}
    for r in df.sort_values("order", kind="stable").itertuples():
        row = rows.setdefault(int(r.order), {"x": r.x, **{n: None for n in names}})
        row[r.series] = round(float(r.value), 4)
    columns = [{"key": "x", "label": x_label, "format": "text"}] + \
              [{"key": n, "label": n, "format": fmt} for n in names]
    return {"columns": columns, "rows": [rows[k] for k in sorted(rows)]}


# ============================================================
# Public API
# ============================================================

def build_visual(df: pd.DataFrame, kind: str, unit: str | None, title: str,
                 x_label: str | None = None) -> tuple[dict | None, dict | None]:
    """Return (chart_spec, chart_table) from one long DataFrame. (None, None) when there is nothing to draw."""
    if kind not in KINDS:
        raise ValueError(f"Unknown chart kind: {kind}")
    if df is None or df.empty:
        return None, None
    x_label = x_label or X_LABELS[kind]
    divisor, unit_title = scale(df["value"], unit)
    table = _table(df, unit, x_label)
    spec = _spec(df, kind, title, x_label, divisor, unit_title, unit)
    return spec, table


def spec_from_legacy(chart: dict | None) -> tuple[dict | None, dict | None]:
    """Old saved answers store {"style", "x_axis_data", "series", "unit"}. Rebuild them the new way."""
    if not chart or not chart.get("series") or not chart.get("x_axis_data"):
        return None, None
    x = chart["x_axis_data"]
    series = {s["name"]: s.get("values") or [] for s in chart["series"]}
    names = list(series)
    if chart.get("style") == "line":
        kind = "forecast" if "Forecast" in series else "trend"
    elif names == ["Current", "Scenario"]:
        kind = "scenario"
    else:
        kind = "compare" if len(names) > 1 else "breakdown"

    if kind == "forecast" and "Actual" in series:
        # Old charts stored the join point inside the forecast series. Drop it; build_visual adds it back.
        actual = series["Actual"]
        series = {n: (v if n == "Actual" else
                      [None if _num(a) is not None else val for a, val in zip(actual, v)])
                  for n, v in series.items()}

    return build_visual(long_frame(x, series), kind, chart.get("unit"), chart.get("title", ""))
