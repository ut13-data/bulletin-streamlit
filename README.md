# bUlleTin: Ask Balaji Pharma's data anything

An AI analytics assistant for **Balaji Pharma**, a fictional Ayurvedic medicine manufacturer in Indore.
The company and its data are synthetic, modelled on 8 years of running a real pharma distribution business.

Ask a business question in plain English ("Forecast revenue for the next 3 months", "Which category has the
lowest margin?", "What if raw material costs rise 10%?") and get an answer with the numbers, a chart,
a recommendation, a confidence level, and a Details section showing the formulas and SQL used.

**Live app:** https://bulletin-app-streamask.streamlit.app/

---

## The core idea

> The AI only interprets the question. Tested Python code calculates every number.

```
Question
  -> AI fills a fixed form (metric, period, filters, operation), validated by Pydantic
  -> Python checks the form against the real data
  -> one set of metric definitions calculates the numbers (SQL + pandas)
  -> code writes the answer text, chart, notes and confidence
  -> AI adds one recommendation sentence (code rejects it if it contains any number)
```

Why: in the first version the AI wrote its own SQL and reported numbers. Testing showed it read "FY24" as
calendar 2024, fitted a forecast on newest-first data (predicting a decline during real growth), and routed
comparison questions to a document search that cannot compare numbers. Moving all calculation into code fixed
this class of error rather than patching prompts one by one.

## What it can answer

| Operation | Example |
|---|---|
| Value | What was net revenue in FY24? (auto-compared with the previous period) |
| Compare | FY25 vs FY24 revenue (adds a like-for-like view when a period is incomplete) |
| Trend | Monthly revenue trend, with peak, low and seasonality |
| Breakdown | Gross margin by category, top 5 products, least reliable supplier |
| Forecast | Revenue for the next 3 months, with a likely range |
| What-if | Price +5%, raw material cost +10%, discount +2 points |
| Definitions | How is DIO calculated? What does the company do? (catalog or business documents) |

Questions outside the metric catalog fall back to AI-written SQL, labelled **Low confidence**, with the SQL shown.

## Findings from building it

1. **Two different cost numbers.** The product table's standard cost is about 37% lower than actual production
   cost. The old dashboard used it for category margins (52 to 55% everywhere) while the company-level margin
   was about 27%. COGS rebuilt from production batch costs matches the finance table every month (within 0.01%).
2. **A range selling below cost.** On actual production cost, Arishta has a gross margin of about -19%,
   and Classical and Syrup are around 4%.
3. **Inventory turnover was a 3-year total.** It showed 50.6, which is really about 17.4 per year.
   Now turnover x DIO = 365, as it should.
4. **Seasonal sales need a seasonal model.** Tested on the last 6 known months, a straight-line forecast
   missed revenue by 12.3% on average; Holt-Winters missed by 2.2% and is chosen automatically.

## Key design decisions

| Decision | Why | Without it |
|---|---|---|
| One metric catalog (`agent/metrics.py`) | Every formula defined once; chat and dashboards agree | Same question, different numbers |
| Fiscal year and partial-period handling (`agent/periods.py`) | FY = April to March; incomplete periods are flagged and compared like-for-like | FY25 (9 months of data) looks like a 15% drop |
| Forecast method chosen by backtest (`agent/forecasting.py`) | Accuracy measured, not assumed; shown to the user | Confident but wrong straight lines |
| Answer text written by code (`agent/operations.py`) | Stated numbers always equal computed numbers | AI can round, swap or invent figures |
| Recommendation may not contain digits (`agent/llm.py`) | Advice can't introduce unverified numbers | Advice contradicting the answer |
| Stateless agent, history in Supabase | Conversations survive restarts and days-later visits | Context lost on every restart |
| Row Level Security + login | Users only see their own chats | Anyone could read all chats |
| Usage table only the server can write | 30 questions per user per day can't be reset by users | Unbounded AI cost |

## Architecture

```
Streamlit (app.py, ui/)          login, chat, charts, Details
   |
Supabase (services/)             auth, chats, messages, usage limit (Row Level Security)
   |
Agent (agent/graph.py, LangGraph) route by intent: metric | definition | ad-hoc | conversation
   |-- parser.py      question -> validated form (Groq, gpt-oss-120b)
   |-- metrics.py     metric catalog -> SQL on bulletin.db (read-only, parameterised)
   |-- operations.py  value / compare / trend / breakdown / forecast / what-if
   |-- forecasting.py Holt-Winters vs seasonal naive vs straight line, by backtest
   |-- rag.py         FAISS search over the 2 business documents
   |-- adhoc.py       fallback AI-written SQL, labelled Low confidence
```

The same `agent/` package also powers the FastAPI backend and the Next.js dashboards, so both front ends
give the same answers.

## Metric definitions (examples)

| Metric | Definition |
|---|---|
| Net revenue | Sum of LineRevenue x (1 - DiscountPct): sales after discounts |
| COGS | Units sold x each product's average production cost (FactProductionBatches) |
| Gross margin | (Net revenue - COGS) / net revenue |
| Inventory turnover | Cost of units sold / average inventory value, annualised |
| DIO | 365 / annualised inventory turnover |
| Supplier on-time delivery | PO lines delivered on time / all PO lines |

All ratios are ratio-of-sums. The full list is in `agent/metrics.py`.

## Testing

```
python -m pytest -q tests      # 50 tests, no API keys needed
python test_agent.py           # checks the real AI reads 16 questions correctly
```

- Every metric is recalculated independently in pandas and must match.
- Gross sales and COGS are reconciled to the company's finance table, month by month.
- Works whether dates are stored as `2024-01-05` or `2024-01-05 00:00:00`.
- Fake-AI tests: messy JSON, unknown metrics, periods with no data, recommendations containing numbers.
- The SQL shown in Details is re-run to confirm it gives the same number.
- Full app tests with a fake Supabase: login, saved chats, follow-ups, rename, delete, daily limit,
  and one user never seeing another's chats.

## Run it locally

```
py -3.12 -m venv venvstream
venvstream\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

`.streamlit/secrets.toml` (never committed):
```
GROQ_API_KEY = "..."
HUGGINGFACEHUB_API_TOKEN = "..."
SUPABASE_URL = "https://<project>.supabase.co"
SUPABASE_ANON_KEY = "..."
SUPABASE_SERVICE_KEY = "..."
```

## Tech stack

Python, SQL (SQLite), pandas, statsmodels, Pydantic, LangGraph, Groq (gpt-oss-120b), FAISS + Hugging Face
embeddings, Streamlit, Altair, Supabase (Postgres, Auth, Row Level Security), pytest.
FastAPI + Next.js for the dashboard version.

## Limits

- Data covers Jan 2022 to Dec 2024; relative words like "last quarter" refer to the latest month with data.
- Forecasts assume past patterns continue; they don't know about launches, price changes or one-off events.
- What-if scenarios are simple driver models (no customer reaction to price changes unless you include it).
- Ad-hoc questions outside the catalog rely on AI-written SQL and are marked Low confidence.

Built by Utkarsh Pathak, with an AI coding assistant. Business rules, metric definitions and validation
of the results are my own.
