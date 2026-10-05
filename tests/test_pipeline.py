"""
End-to-end tests of the agent with a FAKE language model (no API key, no network).

They prove the parts that must hold whatever the LLM says:
  * numbers in the answer come from code, not from the model
  * bad model output is validated and routed safely
  * a recommendation containing invented numbers is rejected
  * periods without data give a clear message, never zeros
"""
import json
from types import SimpleNamespace

import pytest

from agent import graph, llm


def _msg(content):
    return {"ok": True, "message": SimpleNamespace(content=content, tool_calls=None)}


class FakeLLM:
    def __init__(self, parses: dict, recs: list[str] | None = None):
        self.parses = parses
        self.recs = list(recs or ["Plan production ahead of the winter peak."])
        self.calls = []

    def __call__(self, messages, **kwargs):
        system = messages[0]["content"]
        last = messages[-1]["content"]
        self.calls.append(last[:80])
        if "You translate business questions" in system:
            question = last.split("Question:")[-1].strip()
            return _msg(json.dumps(self.parses[question]))
        if "Write ONE short" in messages[0]["content"] or "Write ONE short" in last:
            return _msg(json.dumps({"recommendation": self.recs.pop(0) if self.recs else ""}))
        return _msg("ok")


def q(operation, metrics, periods=(), **kw):
    base = {"operation": operation, "metrics": list(metrics), "periods": list(periods), "dimension": None,
            "filters": {}, "grain": "month", "top_n": None, "sort": "desc", "horizon": 3, "scenario": None}
    base.update(kw)
    return {"intent": "metric", "standalone_question": "", "query": base}


@pytest.fixture
def fake(monkeypatch):
    def install(parses, recs=None):
        f = FakeLLM(parses, recs)
        monkeypatch.setattr(llm, "chat", f)
        return f
    return install


def test_value_answer_uses_computed_numbers(fake):
    fake({"What was revenue in FY24?": q("value", ["net_revenue"], [{"type": "fiscal_year", "value": "FY24"}])})
    r = graph.run_agent("What was revenue in FY24?", [])
    assert r["route_decision"] == "metric" and r["found"]
    assert "₹2.07 Cr" in r["explanation"] and "₹2,07,12,505" in r["explanation"]
    assert "+17.2%" in r["explanation"]           # automatic comparison with FY23
    assert r["confidence"].startswith("High")
    assert r["sql"] and r["definitions"]


def test_alias_metric_names_are_normalised(fake):
    fake({"margin FY24": q("value", ["margin"], [{"type": "fiscal_year", "value": "FY24"}])})
    r = graph.run_agent("margin FY24", [])
    assert "25.1%" in r["explanation"]


def test_unknown_metric_is_not_guessed(fake, monkeypatch):
    fake({"employee attrition?": q("value", ["employee_attrition"])})
    monkeypatch.setattr(graph, "answer_adhoc", lambda question, hist="": {
        "found": False, "explanation": "I don't know.", "sql": [], "rows": None})
    r = graph.run_agent("employee attrition?", [])
    assert r["route_decision"] == "adhoc"


def test_period_without_data_is_explained(fake):
    fake({"revenue 2026": q("value", ["net_revenue"], [{"type": "calendar_year", "value": 2026}])})
    r = graph.run_agent("revenue 2026", [])
    assert not r["found"] and "no data for 2026" in r["explanation"].lower()
    assert r["recommendation"] == ""


def test_recommendation_with_numbers_is_rejected(fake):
    fake({"forecast": q("forecast", ["net_revenue"], horizon=3)},
             recs=["Stock 30% more Chyawanprash.", "Stock 25 lakh units."])
    r = graph.run_agent("forecast", [])
    assert r["recommendation"] == ""              # both attempts contained digits
    assert "Jan 2025" in r["explanation"] and r["chart"]["series"][1]["name"] == "Forecast"
    # New chart fields travel with the response (and get saved to Supabase with it).
    assert r["chart_spec"]["$schema"].endswith("/v6.json")
    assert [c["label"] for c in r["chart_table"]["columns"]][:3] == ["Month", "Actual", "Forecast"]


def test_answers_without_a_chart_have_empty_chart_fields(fake):
    fake({"What was revenue in FY24?": q("value", ["net_revenue"], [{"type": "fiscal_year", "value": "FY24"}])})
    r = graph.run_agent("What was revenue in FY24?", [])
    assert r["chart_spec"] is None and r["chart_table"] is None


def test_recommendation_may_name_products_with_digits(fake):
    fake({"top products": q("breakdown", ["net_revenue"], [{"type": "calendar_year", "value": 2024}],
                            dimension="product", top_n=3)},
         recs=["Protect supply of Balaji Chyawanprash Sugar-Free 500g before the winter peak."])
    r = graph.run_agent("top products", [])
    assert r["recommendation"].startswith("Protect supply")


def test_follow_up_receives_previous_query(fake):
    first = q("value", ["net_revenue"], [{"type": "fiscal_year", "value": "FY24"}])
    fake({"and FY23?": q("value", ["net_revenue"], [{"type": "fiscal_year", "value": "FY23"}])})
    history = [{"question": "revenue FY24", "explanation": "...", "query": first["query"]}]
    r = graph.run_agent("and FY23?", history)
    assert "FY23" in r["explanation"]


def test_turn_limit(fake):
    fake({})
    history = [{"question": "q", "explanation": "a"}] * 10
    r = graph.run_agent("one more", history)
    assert r["route_decision"] == "limit-reached"


def test_compare_partial_year_adds_like_for_like(fake):
    fake({"FY25 vs FY24": q("compare", ["net_revenue"], [{"type": "fiscal_year", "value": "FY24"},
                                                         {"type": "fiscal_year", "value": "FY25"}])})
    r = graph.run_agent("FY25 vs FY24", [])
    assert "Like-for-like" in r["explanation"] and "+19.5%" in r["explanation"]
    assert r["confidence"].startswith("Moderate")


def test_definition_comes_from_catalog(fake):
    fake({"how is DIO calculated?": {"intent": "definition", "definition_metric": "dio_days"}})
    r = graph.run_agent("how is DIO calculated?", [])
    assert r["found"] and "365" in r["explanation"]


def test_invalid_json_from_model_is_retried(monkeypatch):
    replies = iter([_msg("not json"), _msg(json.dumps(q("value", ["net_revenue"],
                                                        [{"type": "fiscal_year", "value": "FY24"}]))),
                    _msg(json.dumps({"recommendation": ""}))])
    monkeypatch.setattr(llm, "chat", lambda messages, **kw: next(replies))
    r = graph.run_agent("revenue FY24", [])
    assert r["found"] and "₹2.07 Cr" in r["explanation"]


def test_nulls_and_bare_strings_from_model_are_tolerated(fake):
    fake({"messy": {"intent": "metric", "query": {
        "operation": "breakdown", "metrics": "revenue", "periods": {"type": "fiscal_year", "value": "FY24"},
        "dimension": "category", "filters": {"distributor": "Malwa"}, "grain": None, "top_n": None,
        "sort": None, "horizon": None, "scenario": None}}})
    r = graph.run_agent("messy", [])
    assert r["found"] and "Malwa Region Distributors" in r["explanation"]


def test_unsupported_request_gets_a_polite_no(fake):
    f = fake({"Can you give the above report as a PDF?": {"intent": "unsupported", "query": None}})
    r = graph.run_agent("Can you give the above report as a PDF?", [])
    assert r["route_decision"] == "unsupported" and not r["found"]
    assert r["explanation"].startswith("Sorry, I can't do that yet.")
    assert r["recommendation"] == "" and len(f.calls) == 1      # no second AI call


def test_brief_is_computed_in_code(fake):
    fake({"Can you give me a brief?": {"intent": "brief", "query": None, "period": None},
          "Give me a report for FY25": {"intent": "brief", "query": None,
                                        "period": [{"type": "fiscal_year", "value": "FY25"}]}})
    r = graph.run_agent("Can you give me a brief?", [])
    assert r["route_decision"] == "brief" and r["found"]
    assert "FY24" in r["explanation"] and "₹2.07 Cr" in r["explanation"] and "+17.2%" in r["explanation"]
    assert "Arishta sells below production cost" in r["explanation"]
    assert r["recommendation"] and r["sql"] and r["confidence"].startswith("High")
    p = graph.run_agent("Give me a report for FY25", [])       # partial year: compared like-for-like
    assert "+19.5%" in p["explanation"] and p["confidence"].startswith("Moderate")
