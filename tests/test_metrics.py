"""
Golden tests for the metric layer. No LLM, no network: run with  python -m pytest -q

Each metric is checked against an INDEPENDENT calculation in plain pandas
(different code path from the SQL in metrics.py), and against the company's
own finance table where one exists.
"""
import numpy as np
import pandas as pd
import pytest

from agent import metrics as M
from agent.db import read_sql
from agent.forecasting import forecast_monthly
from agent.periods import PeriodError, resolve

REL = 1e-9  # identical maths, only floating-point noise allowed


@pytest.fixture(scope="module")
def raw():
    sales = read_sql("SELECT * FROM FactSalesLines")
    sales["d"] = sales["OrderDate"].str[:10]
    prod = read_sql("SELECT * FROM DimProduct")
    batches = read_sql("SELECT * FROM FactProductionBatches")
    cost = batches.groupby("ProductID")["UnitProductionCost"].mean().rename("unit_cost")
    sales = sales.merge(prod[["ProductID", "Category"]], on="ProductID").merge(cost, on="ProductID")
    inv = read_sql("SELECT * FROM FactInventoryWeekly").merge(cost, on="ProductID").merge(
        prod[["ProductID", "Category"]], on="ProductID")
    inv["d"] = inv["WeekEnd"].str[:10]
    fin = read_sql("SELECT * FROM FactFinanceMonthly")
    fin["m"] = fin["MonthYear"].str[:7]
    return {"sales": sales, "inv": inv, "fin": fin}


def _between(df, start, end):
    return df[(df["d"] >= start) & (df["d"] < end)]


# ---------------- periods ----------------

@pytest.mark.parametrize("spec,start,end,partial", [
    ({"type": "fiscal_year", "value": "FY24"}, "2023-04-01", "2024-04-01", False),
    ({"type": "fiscal_year", "value": "2023-24"}, "2023-04-01", "2024-04-01", False),
    ({"type": "fiscal_year", "value": "FY25"}, "2024-04-01", "2025-01-01", True),
    ({"type": "fiscal_year", "value": "latest_complete"}, "2023-04-01", "2024-04-01", False),
    ({"type": "fiscal_quarter", "value": "FY25-Q2"}, "2024-07-01", "2024-10-01", False),
    ({"type": "fiscal_quarter", "value": "Q4 FY24"}, "2024-01-01", "2024-04-01", False),
    ({"type": "quarter", "value": "Q3 2024"}, "2024-07-01", "2024-10-01", False),
    ({"type": "month", "value": "Nov 2024"}, "2024-11-01", "2024-12-01", False),
    ({"type": "last_n_months", "n": 6}, "2024-07-01", "2025-01-01", False),
    ({"type": "range", "start": "2023-01", "end": "2023-06"}, "2023-01-01", "2023-07-01", False),
    ({"type": "calendar_year", "value": "previous"}, "2023-01-01", "2024-01-01", False),
])
def test_period_resolution(spec, start, end, partial):
    p = resolve(spec)
    assert (p.start_str, p.end_str, p.is_partial) == (start, end, partial)


@pytest.mark.parametrize("spec", [{"type": "calendar_year", "value": 2026}, {"type": "month", "value": "2021-05"}])
def test_period_without_data_is_an_error_not_zero(spec):
    with pytest.raises(PeriodError, match="no data"):
        resolve(spec)


# ---------------- sales metrics ----------------

def test_net_revenue_fy24_matches_pandas(raw):
    s = _between(raw["sales"], "2023-04-01", "2024-04-01")
    expected = (s.LineRevenue * (1 - s.DiscountPct)).sum()
    assert M.value("net_revenue", resolve({"type": "fiscal_year", "value": "FY24"})) == pytest.approx(expected, rel=REL)


def test_gross_sales_equals_finance_table_revenue_every_month(raw):
    """FactFinanceMonthly.Revenue is revenue BEFORE discounts."""
    r = M.compute(["gross_sales"], resolve({"type": "all"}), grain="month").df.set_index("period")["gross_sales"]
    fin = raw["fin"].set_index("m")["Revenue"]
    assert np.allclose(r.loc[fin.index].values, fin.values, rtol=1e-9)


def test_cogs_reconciles_to_finance_table_every_month(raw):
    """COGS basis (average production cost) reconciles to the finance table within 0.01%."""
    r = M.compute(["cogs"], resolve({"type": "all"}), grain="month").df.set_index("period")["cogs"]
    fin = raw["fin"].set_index("m")["COGS"]
    assert np.allclose(r.loc[fin.index].values, fin.values, rtol=1e-4)


def test_gross_margin_is_ratio_of_sums(raw):
    s = _between(raw["sales"], "2023-04-01", "2024-04-01")
    net = (s.LineRevenue * (1 - s.DiscountPct)).sum()
    cogs = (s.Quantity * s.unit_cost).sum()
    got = M.value("gross_margin_pct", resolve({"type": "fiscal_year", "value": "FY24"}))
    assert got == pytest.approx((net - cogs) / net * 100, rel=REL)


def test_discount_pct(raw):
    s = raw["sales"]
    expected = (s.LineRevenue * s.DiscountPct).sum() / s.LineRevenue.sum() * 100
    assert M.value("discount_pct", resolve({"type": "all"})) == pytest.approx(expected, rel=REL)


def test_distinct_counts(raw):
    s = _between(raw["sales"], "2024-01-01", "2025-01-01")
    p = resolve({"type": "calendar_year", "value": 2024})
    assert M.value("orders", p) == s.OrderID.nunique()
    assert M.value("active_customers", p) == s.CustomerID.nunique()


def test_category_breakdown_adds_up_to_total():
    p = resolve({"type": "fiscal_year", "value": "FY24"})
    by_cat = M.compute(["net_revenue", "cogs"], p, dims=["category"]).df
    total = M.compute(["net_revenue", "cogs"], p).df.iloc[0]
    assert by_cat.net_revenue.sum() == pytest.approx(total.net_revenue, rel=REL)
    assert by_cat.cogs.sum() == pytest.approx(total.cogs, rel=REL)


def test_category_margins_are_consistent_with_company_margin():
    """The old dashboard showed ~54% by category but ~27% overall. Now the revenue-weighted category
    margins must reproduce the company margin exactly."""
    p = resolve({"type": "fiscal_year", "value": "FY24"})
    df = M.compute(["net_revenue", "gross_margin_pct"], p, dims=["category"]).df
    weighted = (df.gross_margin_pct * df.net_revenue).sum() / df.net_revenue.sum()
    assert weighted == pytest.approx(M.value("gross_margin_pct", p), rel=1e-9)


def test_fiscal_quarter_buckets(raw):
    df = M.compute(["net_revenue"], resolve({"type": "fiscal_year", "value": "FY24"}), grain="fiscal_quarter").df
    assert df.period.tolist() == ["FY24-Q1", "FY24-Q2", "FY24-Q3", "FY24-Q4"]
    s = _between(raw["sales"], "2023-10-01", "2024-01-01")
    assert df.set_index("period").loc["FY24-Q3", "net_revenue"] == pytest.approx(
        (s.LineRevenue * (1 - s.DiscountPct)).sum(), rel=REL)


def test_filters_match_real_values_and_block_injection():
    assert M.resolve_filters(["net_revenue"], {"product": ["chyawanprash"]})["product"] == [
        "Balaji Chyawanprash 500g", "Balaji Chyawanprash Sugar-Free 500g"]
    with pytest.raises(M.MetricError):
        M.resolve_filters(["net_revenue"], {"category": ["x' OR 1=1 --"]})
    with pytest.raises(M.MetricError):   # inventory can't be split by distributor
        M.resolve_filters(["inventory_turnover"], {"distributor": ["Indore Central Distributors"]})


def test_filtered_value_matches_pandas(raw):
    s = _between(raw["sales"], "2024-01-01", "2025-01-01")
    s = s[s.Category == "Churna"]
    f = M.resolve_filters(["units_sold"], {"category": ["churna"]})
    assert M.value("units_sold", resolve({"type": "calendar_year", "value": 2024}), f) == s.Quantity.sum()


# ---------------- inventory metrics ----------------

def test_inventory_turnover_and_dio(raw):
    i = _between(raw["inv"], "2023-04-01", "2024-04-01")
    weeks = i.WeekEnd.nunique()
    cogs = (i.Sold * i.unit_cost).sum()
    avg_inv = (i.ClosingStock * i.unit_cost).sum() / weeks        # mean weekly total inventory value
    turnover = cogs / avg_inv * 365 / (weeks * 7)
    p = resolve({"type": "fiscal_year", "value": "FY24"})
    assert M.value("inventory_turnover", p) == pytest.approx(turnover, rel=REL)
    assert M.value("dio_days", p) == pytest.approx(365 / turnover, rel=REL)
    assert M.value("avg_inventory_value", p) == pytest.approx(avg_inv, rel=REL)


def test_turnover_is_annualised_so_it_agrees_with_dio():
    """Old dashboard: turnover 50.6 (3-year total) but DIO 21.7 days. 365/50.6 = 7.2, inconsistent."""
    p = resolve({"type": "all"})
    assert M.value("inventory_turnover", p) * M.value("dio_days", p) == pytest.approx(365, rel=1e-9)


# ---------------- procurement / production ----------------

def test_on_time_delivery(raw):
    po = read_sql("SELECT * FROM FactPurchaseOrderLines")
    po = po[(po.OrderDate.str[:10] >= "2024-01-01") & (po.OrderDate.str[:10] < "2025-01-01")]
    expected = (po.Status == "Delivered On Time").mean() * 100
    assert M.value("on_time_delivery_pct", resolve({"type": "calendar_year", "value": 2024})) == pytest.approx(expected)


def test_reject_rate():
    b = read_sql("SELECT * FROM FactProductionBatches")
    b = b[(b.ProductionWeekEnd.str[:10] >= "2023-04-01") & (b.ProductionWeekEnd.str[:10] < "2024-04-01")]
    expected = b.RejectQty.sum() / b.QuantityProduced.sum() * 100
    assert M.value("reject_rate_pct", resolve({"type": "fiscal_year", "value": "FY24"})) == pytest.approx(expected)


# ---------------- forecasting ----------------

def test_forecast_beats_straight_line_on_revenue():
    df = M.compute(["net_revenue"], resolve({"type": "all"}), grain="month").df
    f = forecast_monthly(pd.Series(df.net_revenue.values, index=df.period.values), horizon=3)
    assert list(f.forecast.index) == ["2025-01", "2025-02", "2025-03"]
    assert f.method != "linear_trend"
    assert f.backtest_mape < f.candidates["linear_trend"]
    assert (f.low <= f.forecast).all() and (f.forecast <= f.high).all()


# ---------------- SQL shown to users ----------------

def test_details_sql_is_specific_to_the_question():
    """Details must show the query that produced THIS answer: real dates, only the columns and joins used."""
    fy24 = resolve({"type": "fiscal_year", "value": "FY24"})
    sql = M.compute(["net_revenue"], fy24).sql[0]
    assert "'2023-04-01'" in sql and "'2024-04-01'" in sql and ":start" not in sql
    assert "net_revenue" in sql and "cogs" not in sql and "units_sold" not in sql
    assert "DimCustomer" not in sql and "product_cost" not in sql

    margin_sql = M.compute(["gross_margin_pct"], fy24, dims=["category"]).sql[0]
    assert "product_cost" in margin_sql and "GROUP BY category" in margin_sql

    f = M.resolve_filters(["net_revenue"], {"distributor": ["Malwa"]})
    dist_sql = M.compute(["net_revenue"], fy24, filters=f).sql[0]
    assert "DimDistributor" in dist_sql and "'Malwa Region Distributors'" in dist_sql


def test_shown_sql_returns_the_same_number():
    """Running the SQL exactly as displayed gives the same value the app reported."""
    fy24 = resolve({"type": "fiscal_year", "value": "FY24"})
    res = M.compute(["gross_margin_pct"], fy24)
    raw = read_sql(res.sql[0]).iloc[0]
    assert (raw.net_revenue - raw.cogs) / raw.net_revenue * 100 == pytest.approx(res.df.gross_margin_pct.iloc[0], rel=REL)
