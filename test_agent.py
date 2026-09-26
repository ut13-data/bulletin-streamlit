"""
Live accuracy check with the real LLM. Run from the repo root:  python test_agent.py

Part 1 checks that each question is UNDERSTOOD correctly (operation, metric,
period, filters). Once the question is understood, the numbers come from the
tested metric layer, so this is where accuracy can still go wrong.
Part 2 prints three full answers so you can read them.

Add a line to QUESTIONS whenever a real user question is misread; that's how
the prompt gets better without guesswork.
"""
from agent.graph import run_agent
from agent.parser import parse
from agent.periods import resolve


def period_shorts(q):
    return [resolve(p).short for p in q.periods]


# (question, history, check on the parsed result)
QUESTIONS = [
    ("What was total revenue in FY24?", [],
     lambda p: p.query.operation == "value" and p.query.metrics == ["net_revenue"] and period_shorts(p.query) == ["FY24"]),
    ("How much did revenue grow in FY24?", [],
     lambda p: p.query.operation == "compare" and sorted(period_shorts(p.query)) == ["FY23", "FY24"]),
    ("Compare gross margin FY23 vs FY24", [],
     lambda p: p.query.operation == "compare" and p.query.metrics == ["gross_margin_pct"]),
    ("Which category has the lowest margin?", [],
     lambda p: p.query.operation == "breakdown" and p.query.dimension == "category" and p.query.sort == "asc"),
    ("Top 5 products by sales in 2024", [],
     lambda p: p.query.operation == "breakdown" and p.query.dimension == "product" and p.query.top_n == 5
     and period_shorts(p.query) == ["2024"]),
    ("Show monthly revenue trend", [],
     lambda p: p.query.operation == "trend" and p.query.grain == "month"),
    ("Forecast revenue for the next 3 months", [],
     lambda p: p.query.operation == "forecast" and p.query.horizon == 3 and p.query.metrics == ["net_revenue"]),
    ("Predict syrup sales for next 6 months", [],
     lambda p: p.query.operation == "forecast" and p.query.horizon == 6 and p.query.filters.get("category") == ["Syrup"]),
    ("What is our DIO?", [],
     lambda p: p.query.operation == "value" and p.query.metrics == ["dio_days"]),
    ("What if we raise prices by 5%?", [],
     lambda p: p.query.operation == "scenario" and p.query.scenario.driver == "price" and p.query.scenario.change == 5),
    ("What if raw material costs go up 10%?", [],
     lambda p: p.query.operation == "scenario" and p.query.scenario.driver == "unit_cost"),
    ("Which supplier is least reliable?", [],
     lambda p: p.query.operation == "breakdown" and p.query.dimension == "supplier"
     and p.query.metrics[0] in ("on_time_delivery_pct", "avg_days_late")),
    ("Revenue for tablets last quarter", [],
     lambda p: p.query.filters.get("category") == ["Vati"] and period_shorts(p.query) == ["2024-Q4"]),
    ("How is gross margin calculated?", [],
     lambda p: p.intent == "definition" and p.definition_metric == "gross_margin_pct"),
    ("How does that compare to FY23?",
     [{"question": "What was revenue in FY24?", "explanation": "Net revenue for FY24 was ₹2.07 Cr.",
       "query": {"operation": "value", "metrics": ["net_revenue"], "periods": [{"type": "fiscal_year", "value": "FY24"}]}}],
     lambda p: p.query.operation == "compare" and p.query.metrics == ["net_revenue"]
     and sorted(period_shorts(p.query)) == ["FY23", "FY24"]),
    ("What is the weather in Indore?", [], lambda p: p.intent == "off_topic"),
]


def part1():
    passed = 0
    for question, history, check in QUESTIONS:
        parsed, err = parse(question, history)
        try:
            ok = parsed is not None and check(parsed)
        except Exception as e:
            ok, err = False, f"{type(e).__name__}: {e}"
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {question}")
        if not ok:
            print(f"      parsed: {parsed.model_dump() if parsed else None}  error: {err}")
    print(f"\n{passed}/{len(QUESTIONS)} questions understood correctly\n")


def part2():
    for question in ["What was total revenue in FY24?",
                     "Forecast revenue for the next 3 months",
                     "Gross margin by category for FY24"]:
        r = run_agent(question, [])
        print("=" * 80, f"\nQ: {question}\n")
        print(r["explanation"])
        for note in r["notes"]:
            print(f"  note: {note}")
        print(f"\nRecommendation: {r['recommendation']}\nConfidence: {r['confidence']}\n")


if __name__ == "__main__":
    part1()
    part2()
