"""Batch aggregation for high-dividend stock lists.

All list APIs use this module so price, DPS, percentile and valuation fields
share one as-of date and do not issue SQL from inside a per-stock loop.
"""
from collections import defaultdict
from datetime import date, timedelta
from math import pow
from statistics import median
from typing import Optional

from sqlalchemy import func

from database.models import (
    DailyPrice,
    Dividend,
    FinancialStatement,
    Stock,
    ValuationHistory,
)


def _grade(consecutive: int) -> str:
    if consecutive >= 15:
        return "S"
    if consecutive >= 10:
        return "A"
    if consecutive >= 5:
        return "B"
    if consecutive >= 3:
        return "C"
    return "D"


def _percentile(value: float, values: list[float]) -> Optional[float]:
    if value is None or not values:
        return None
    return round(sum(v < value for v in values) / len(values) * 100, 1)


def _quantile(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


def _year_metrics(rows, as_of_year: int):
    yearly = defaultdict(dict)
    for symbol, report_year, dps in rows:
        if report_year and dps and dps > 0:
            yearly[symbol][int(report_year)] = float(dps)

    metrics = {}
    for symbol, values in yearly.items():
        latest_year = min(max(values), as_of_year - 1)
        consecutive = 0
        for year in range(latest_year, latest_year - 20, -1):
            if values.get(year, 0) > 0:
                consecutive += 1
            else:
                break

        cagr_5y = None
        start = values.get(latest_year - 5)
        end = values.get(latest_year)
        if start and start > 0 and end and end > 0:
            cagr_5y = round((pow(end / start, 1 / 5) - 1) * 100, 2)

        metrics[symbol] = {
            "consecutive_years": consecutive,
            "stability_grade": _grade(consecutive),
            "cagr_5y": cagr_5y,
            "latest_report_year": latest_year,
            "latest_year_dps": values.get(latest_year),
        }
    return metrics


def build_high_dividend_snapshot(session, as_of: Optional[date] = None) -> list[dict]:
    """Return one normalized row per active stock with positive TTM DPS."""
    as_of = as_of or date.today()
    ttm_start = as_of - timedelta(days=365)

    stocks = {
        s.symbol: s
        for s in session.query(Stock).filter(Stock.status == "active").all()
    }

    price_sub = session.query(
        DailyPrice.symbol,
        func.max(DailyPrice.date).label("max_date"),
    ).filter(DailyPrice.date <= as_of).group_by(DailyPrice.symbol).subquery()
    prices = {
        p.symbol: p
        for p in session.query(DailyPrice).join(
            price_sub,
            (DailyPrice.symbol == price_sub.c.symbol)
            & (DailyPrice.date == price_sub.c.max_date),
        ).all()
        if p.close and p.close > 0
    }

    ttm_rows = session.query(
        Dividend.symbol,
        func.sum(Dividend.cash_div_per_share),
    ).filter(
        Dividend.status == "executed",
        Dividend.ex_date >= ttm_start,
        Dividend.ex_date <= as_of,
        Dividend.cash_div_per_share > 0,
    ).group_by(Dividend.symbol).all()
    ttm_dps = {symbol: float(dps) for symbol, dps in ttm_rows if dps}

    year_rows = session.query(
        Dividend.symbol,
        func.sum(Dividend.cash_div_per_share),
    ).filter(
        Dividend.status == "executed",
        Dividend.ex_date >= date(as_of.year, 1, 1),
        Dividend.ex_date <= as_of,
        Dividend.cash_div_per_share > 0,
    ).group_by(Dividend.symbol).all()
    this_year_dps = {symbol: float(dps) for symbol, dps in year_rows if dps}

    yearly_rows = session.query(
        Dividend.symbol,
        Dividend.report_year,
        func.sum(Dividend.cash_div_per_share),
    ).filter(
        Dividend.status.in_(["executed", "confirmed"]),
        Dividend.report_year.isnot(None),
        Dividend.cash_div_per_share > 0,
    ).group_by(Dividend.symbol, Dividend.report_year).all()
    year_metrics = _year_metrics(yearly_rows, as_of.year)

    fin_sub = session.query(
        FinancialStatement.symbol,
        func.max(FinancialStatement.report_date).label("max_date"),
    ).filter(FinancialStatement.report_date <= as_of).group_by(
        FinancialStatement.symbol
    ).subquery()
    latest_fin = {}
    for fin in session.query(FinancialStatement).join(
        fin_sub,
        (FinancialStatement.symbol == fin_sub.c.symbol)
        & (FinancialStatement.report_date == fin_sub.c.max_date),
    ).all():
        latest_fin.setdefault(fin.symbol, fin)

    valuation_sub = session.query(
        ValuationHistory.symbol,
        func.max(ValuationHistory.date).label("max_date"),
    ).filter(ValuationHistory.date <= as_of).group_by(
        ValuationHistory.symbol
    ).subquery()
    latest_valuation = {}
    for val in session.query(ValuationHistory).join(
        valuation_sub,
        (ValuationHistory.symbol == valuation_sub.c.symbol)
        & (ValuationHistory.date == valuation_sub.c.max_date),
    ).all():
        latest_valuation.setdefault(val.symbol, val)

    history = defaultdict(list)
    history_start = as_of - timedelta(days=5 * 365)
    for symbol, value in session.query(
        ValuationHistory.symbol, ValuationHistory.dividend_yield_ttm
    ).filter(
        ValuationHistory.date >= history_start,
        ValuationHistory.date <= as_of,
        ValuationHistory.dividend_yield_ttm > 0,
    ).all():
        history[symbol].append(float(value))

    rows = []
    for symbol, dps in ttm_dps.items():
        stock = stocks.get(symbol)
        price_row = prices.get(symbol)
        if not stock or not price_row:
            continue
        current_yield = round(dps / float(price_row.close) * 100, 4)
        fin = latest_fin.get(symbol)
        val = latest_valuation.get(symbol)
        pe = float(val.pe_ttm) if val and val.pe_ttm and val.pe_ttm > 0 else None
        pe_source = "valuation_history" if pe is not None else None
        if pe is None and fin and fin.eps and fin.eps > 0:
            pe = round(float(price_row.close) / float(fin.eps), 2)
            pe_source = "latest_report_eps"

        metrics = year_metrics.get(symbol, {})
        payout_ratio = None
        total_dividend = None
        latest_year_dps = metrics.get("latest_year_dps")
        if latest_year_dps and stock.total_shares and stock.total_shares > 0:
            total_dividend = latest_year_dps * float(stock.total_shares)
        if total_dividend and fin and fin.net_profit and fin.net_profit > 0:
            payout_ratio = round(total_dividend / float(fin.net_profit) * 100, 2)

        triggered = 0
        if fin and fin.net_profit is not None and fin.net_profit < 0:
            triggered += 1
        if fin and fin.net_profit_yoy is not None and fin.net_profit_yoy < -30:
            triggered += 1
        if fin and fin.debt_ratio is not None and fin.debt_ratio > 70 and current_yield >= 6:
            triggered += 1
        if payout_ratio is not None and payout_ratio > 100:
            triggered += 1
        if total_dividend and fin and fin.free_cf is not None and fin.free_cf < total_dividend:
            triggered += 1
        risk = "LOW" if triggered == 0 else "MEDIUM" if triggered < 3 else "HIGH"

        rows.append({
            "symbol": symbol,
            "name": stock.name,
            "exchange": stock.exchange,
            "industry": stock.industry or "",
            "price": float(price_row.close),
            "price_date": str(price_row.date),
            "market_cap": stock.total_market_cap,
            "pe_ttm": pe,
            "pe_source": pe_source,
            "ttm_dps": round(dps, 4),
            "dps": round(dps, 4),
            "this_year_dps": round(this_year_dps.get(symbol, 0.0), 4),
            "ttm_yield": current_yield,
            "roe": round(float(fin.roe), 2) if fin and fin.roe is not None else None,
            "financial_report_date": str(fin.report_date) if fin else None,
            "payout_ratio": payout_ratio,
            "consecutive_years": metrics.get("consecutive_years", 0),
            "stability_grade": metrics.get("stability_grade", "D"),
            "cagr_5y": metrics.get("cagr_5y"),
            "trap_risk": risk,
        })

    market_yields = [r["ttm_yield"] for r in rows]
    market_p50 = _quantile(market_yields, 0.5)
    market_p90 = _quantile(market_yields, 0.9)
    for row in rows:
        values = history.get(row["symbol"], [])
        if len(values) >= 5:
            row["yield_percentile"] = _percentile(row["ttm_yield"], values)
            row["p50_yield"] = round(median(values), 2)
            row["p90_yield"] = _quantile(values, 0.9)
            row["percentile_basis"] = "historical_5y"
        else:
            row["yield_percentile"] = _percentile(row["ttm_yield"], market_yields)
            row["p50_yield"] = market_p50
            row["p90_yield"] = market_p90
            row["percentile_basis"] = "market_cross_section"
    return rows
