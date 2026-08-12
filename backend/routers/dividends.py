"""Dividend ranking, opportunity and calendar APIs."""
from datetime import date, timedelta

from fastapi import APIRouter, Query

from backend.services.high_dividend import build_high_dividend_snapshot
from database.engine import get_session
from database.models import Dividend, Stock

router = APIRouter()

SORT_FIELDS = {
    "ttm_yield", "ttm_dps", "this_year_dps", "pe_ttm",
    "consecutive_years", "cagr_5y", "market_cap", "symbol",
}


@router.get("/ranking")
def dividend_ranking(
    min_yield: float = Query(3, ge=0, description="最低股息率(%)"),
    min_years: int = Query(3, ge=0, description="最低连续分红年数"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str = Query("ttm_yield"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
):
    """High-dividend ranking using one consistent as-of date."""
    session = get_session()
    try:
        rows = [
            row for row in build_high_dividend_snapshot(session)
            if row["ttm_yield"] >= min_yield
            and row["consecutive_years"] >= min_years
        ]
        field = sort_by if sort_by in SORT_FIELDS else "ttm_yield"
        rows.sort(
            key=lambda row: (row.get(field) is not None, row.get(field) or 0),
            reverse=sort_dir == "desc",
        )
        start = (page - 1) * page_size
        return {
            "status": "ok",
            "data": {
                "total": len(rows),
                "page": page,
                "page_size": page_size,
                "as_of": str(date.today()),
                "items": rows[start:start + page_size],
            },
        }
    finally:
        session.close()


@router.get("/opportunities")
def dividend_opportunities(
    percentile_threshold: float = Query(80, ge=0, le=100, description="股息率百分位阈值"),
    min_yield: float = Query(0, ge=0, description="最低股息率(%)"),
    limit: int = Query(50, ge=1, le=200),
):
    """Stocks whose current yield is high versus history or the current market."""
    session = get_session()
    try:
        rows = [
            row for row in build_high_dividend_snapshot(session)
            if row.get("yield_percentile") is not None
            and row["yield_percentile"] >= percentile_threshold
            and row["ttm_yield"] >= min_yield
        ]
        rows.sort(key=lambda row: (row["yield_percentile"], row["ttm_yield"]), reverse=True)
        return {
            "status": "ok",
            "data": {
                "total": len(rows),
                "threshold": percentile_threshold,
                "items": rows[:limit],
            },
        }
    finally:
        session.close()


@router.get("/calendar")
def dividend_calendar(days: int = Query(30, ge=0, le=366, description="未来天数")):
    """Upcoming confirmed dividend events."""
    session = get_session()
    try:
        today = date.today()
        end = today + timedelta(days=days)
        events = session.query(Dividend, Stock.name).join(
            Stock, Stock.symbol == Dividend.symbol
        ).filter(
            Dividend.ex_date >= today,
            Dividend.ex_date <= end,
            Dividend.status.in_(["confirmed", "approved"]),
        ).order_by(Dividend.ex_date).all()
        return {
            "status": "ok",
            "data": {"items": [{
                "symbol": dividend.symbol,
                "name": name,
                "ex_date": str(dividend.ex_date),
                "dps": dividend.cash_div_per_share,
                "status": dividend.status,
            } for dividend, name in events]},
        }
    finally:
        session.close()
