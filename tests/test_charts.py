"""
Tests for agent/charts.py: one Vega-Lite spec + one table per chart answer.

They prove:
  * every spec is valid Vega-Lite (checked against the schema Altair ships with)
  * the table and the chart hold the same numbers (same DataFrame, no drift)
  * the new visual shows the same numbers as the old `chart` dict (nothing changed in migration)
  * the forecast has Actual, Forecast and the band, joined at the last actual month
  * old saved `chart` dicts from Supabase still render
"""
import json

import altair as alt
import pytest

from agent import charts as C
from agent.operations import MetricQuery, run

FY24 = {"type": "fiscal_year", "value": "FY24"}
FY23 = {"type": "fiscal_year", "value": "FY23"}

QUERIES = {
    "compare": {"operation": "compare", "metrics": ["net_revenue"], "periods": [FY23, FY24]},
    "trend": {"operation": "trend", "metrics": ["net_revenue"], "periods": [FY24], "grain": "month"},
    "breakdown": {"operation": "breakdown", "metrics": ["net_revenue"], "periods": [FY24], "dimension": "product"},
    "forecast": {"operation": "forecast", "metrics": ["net_revenue"], "horizon": 3},
    "scenario": {"operation": "scenario", "metrics": ["gross_profit"],
                 "scenario": {"driver": "price", "change": 5}},
}


def validate(spec: dict):
    """Raises if the spec is not valid Vega-Lite v6, or not JSON-serialisable (Supabase stores JSON)."""
    (alt.LayerChart if "layer" in spec else alt.Chart).from_dict(spec)
    json.dumps(spec)


def spec_points(spec: dict) -> dict[tuple[str, str], float]:
    """{(x, series): raw value} from the spec data, join points excluded."""
    return {(v["x"], v["series"]): v["raw"] for v in spec["data"]["values"] if not v["join"]}


def table_points(table: dict) -> dict[tuple[str, str], float]:
    keys = [c["key"] for c in table["columns"][1:]]
    return {(r["x"], k): r[k] for r in table["rows"] for k in keys if r[k] is not None}


def legacy_points(chart: dict) -> dict[tuple[str, str], float]:
    """Old chart dict, with the forecast join point removed."""
    out = {}
    actual = next((s["values"] for s in chart["series"] if s["name"] == "Actual"), None)
    for s in chart["series"]:
        for i, (x, v) in enumerate(zip(chart["x_axis_data"], s["values"])):
            joined = actual is not None and s["name"] != "Actual" and actual[i] is not None
            if v is not None and not joined:
                out[(x, s["name"])] = v
    return out


@pytest.fixture(scope="module")
def answers():
    return {kind: run(MetricQuery.model_validate(body)) for kind, body in QUERIES.items()}


# ============================================================
# Real answers from operations.py
# ============================================================

@pytest.mark.parametrize("kind", list(QUERIES))
def test_every_spec_is_valid_vega_lite(answers, kind):
    ans = answers[kind]
    assert ans.chart_spec and ans.chart_table
    validate(ans.chart_spec)
    assert ans.chart_spec["$schema"].endswith("/v6.json")
    assert ans.chart_spec["width"] == "container" and ans.chart_spec["background"] == "transparent"


@pytest.mark.parametrize("kind", list(QUERIES))
def test_table_and_chart_hold_the_same_numbers(answers, kind):
    ans = answers[kind]
    # Same source, same rounding: the numbers must be exactly equal, not just close.
    assert spec_points(ans.chart_spec) == table_points(ans.chart_table)
    # And the axis divides them by the right factor.
    divisor = ans.chart_spec["usermeta"]["bulletin"]["divisor"]
    assert ans.chart_spec["transform"][0] == {"calculate": f"datum.raw / {divisor:g}", "as": "value"}


@pytest.mark.parametrize("kind", list(QUERIES))
def test_new_visual_matches_old_chart(answers, kind):
    ans = answers[kind]
    old, new = legacy_points(ans.chart), table_points(ans.chart_table)
    assert old.keys() == new.keys()
    for key in old:
        assert old[key] == pytest.approx(new[key], rel=1e-6, abs=1e-3)


def test_forecast_has_band_and_joins_at_last_actual(answers):
    spec, table = answers["forecast"].chart_spec, answers["forecast"].chart_table
    names = {v["series"] for v in spec["data"]["values"]}
    assert {"Actual", "Forecast", "Likely low", "Likely high"} <= names
    assert len(spec["layer"]) == 2                                   # band + lines

    actual = [v for v in spec["data"]["values"] if v["series"] == "Actual"]
    last = max(actual, key=lambda v: v["order"])
    first_fc = min((v for v in spec["data"]["values"] if v["series"] == "Forecast"), key=lambda v: v["order"])
    assert first_fc["x"] == last["x"] and first_fc["raw"] == last["raw"] and first_fc["join"]

    # The table does not repeat the actual value in the Forecast column.
    row = next(r for r in table["rows"] if r["x"] == last["x"])
    assert row["Forecast"] is None
    assert [c["label"] for c in table["columns"]] == ["Month", "Actual", "Forecast", "Likely low", "Likely high"]


def test_breakdown_by_product_is_horizontal(answers):
    spec = answers["breakdown"].chart_spec
    assert spec["usermeta"]["bulletin"]["mark"] == "bar_horizontal"
    assert spec["encoding"]["y"]["field"] == "x"


def test_rupee_axis_is_scaled_in_python(answers):
    meta = answers["compare"].chart_spec["usermeta"]["bulletin"]
    assert meta["divisor"] == 1e7 and meta["unit_title"] == "₹ Crore"
    assert answers["compare"].chart_table["columns"][1]["format"] == "inr"


# ============================================================
# Unit tests on charts.py itself (no data files needed)
# ============================================================

def test_choose_mark_rules():
    assert C.choose_mark("trend", ["a"], 1) == "line"
    assert C.choose_mark("forecast", ["a"], 2) == "forecast"
    assert C.choose_mark("breakdown", list("abcdefg"), 1) == "bar_horizontal"          # more than 6
    assert C.choose_mark("breakdown", ["A very long product name"], 1) == "bar_horizontal"
    assert C.choose_mark("breakdown", ["Syrup", "Tel"], 1) == "bar"
    assert C.choose_mark("compare", list("abcdefg"), 1) == "bar"                        # periods stay vertical


def test_scale():
    assert C.scale([2.5e7], "inr") == (1e7, "₹ Crore")
    assert C.scale([3e5], "inr") == (1e5, "₹ Lakh")
    assert C.scale([999], "inr") == (1.0, "₹")
    assert C.scale([25.0], "pct") == (1.0, "%")


def test_nothing_to_draw():
    assert C.build_visual(C.long_frame(["a"], {"s": [None]}), "trend", "inr", "t") == (None, None)
    assert C.spec_from_legacy(None) == (None, None)
    assert C.spec_from_legacy({"style": "bar", "series": [], "x_axis_data": []}) == (None, None)


def _legacy_forecast(with_band: bool) -> dict:
    x = ["2024-10", "2024-11", "2024-12", "2025-01", "2025-02"]
    series = [{"name": "Actual", "values": [2.3e6, 2.6e6, 2.7e6, None, None]},
              {"name": "Forecast", "values": [None, None, 2.7e6, 2.4e6, 2.3e6]}]
    if with_band:
        series += [{"name": "Likely low", "values": [None, None, 2.7e6, 2.2e6, 2.0e6]},
                   {"name": "Likely high", "values": [None, None, 2.7e6, 2.6e6, 2.6e6]}]
    return {"style": "line", "title": "Net revenue: actual and forecast", "x_axis_data": x,
            "series": series, "unit": "inr"}


def test_legacy_forecast_still_renders():
    spec, table = C.spec_from_legacy(_legacy_forecast(with_band=True))
    validate(spec)
    assert "layer" in spec
    assert table["rows"][2] == {"x": "2024-12", "Actual": 2.7e6, "Forecast": None,
                                "Likely low": None, "Likely high": None}
    joins = [v for v in spec["data"]["values"] if v["join"]]
    assert {v["series"] for v in joins} == {"Forecast", "Likely low", "Likely high"}


def test_legacy_forecast_without_band_renders():
    """React-era saves had the band stripped by for_react()."""
    spec, _ = C.spec_from_legacy(_legacy_forecast(with_band=False))
    validate(spec)
    assert "layer" not in spec


@pytest.mark.parametrize("chart, kind", [
    ({"style": "bar", "title": "t", "x_axis_data": ["FY23", "FY24"], "unit": "inr",
      "series": [{"name": "Net revenue", "values": [1.7e7, 2.07e7]}]}, "breakdown"),
    ({"style": "bar", "title": "t", "x_axis_data": ["Net revenue", "COGS", "Gross profit"], "unit": "inr",
      "series": [{"name": "Current", "values": [2e7, 1.5e7, 5e6]},
                 {"name": "Scenario", "values": [2.1e7, 1.5e7, 6e6]}]}, "scenario"),
    ({"style": "line", "title": "t", "x_axis_data": ["2024-Q1", "2024-Q2*"], "unit": "pct",
      "series": [{"name": "Gross margin", "values": [25.1, 26.0]}]}, "trend"),
])
def test_legacy_bar_and_line_charts_render(chart, kind):
    spec, table = C.spec_from_legacy(chart)
    validate(spec)
    assert spec["usermeta"]["bulletin"]["kind"] == kind
    assert table_points(table) == legacy_points(chart)
