"""Market overview API."""
from collections import defaultdict

from fastapi import APIRouter
from sqlalchemy import func

from backend.services.high_dividend import build_high_dividend_snapshot
from database.engine import get_session
from database.models import Dividend, Stock

router = APIRouter()


@router.get("/overview")
def market_overview():
    session = get_session()
    try:
        rows = build_high_dividend_snapshot(session)
        distribution = {threshold: 0 for threshold in (3, 4, 5, 6, 7, 8)}
        industries = defaultdict(list)
        for row in rows:
            for threshold in distribution:
                if row["ttm_yield"] >= threshold:
                    distribution[threshold] += 1
            industries[row["industry"] or "未知"].append(row["ttm_yield"])
        industry_avg = sorted(
            ((name, round(sum(values) / len(values), 2)) for name, values in industries.items() if len(values) >= 2),
            key=lambda item: item[1], reverse=True,
        )[:20]
        latest_price_date = max((row["price_date"] for row in rows), default=None)
        return {"status": "ok", "data": {
            "total_stocks": session.query(Stock).filter(Stock.status == "active").count(),
            "stocks_with_dividend": session.query(func.count(func.distinct(Dividend.symbol))).filter(Dividend.status.in_(["executed", "confirmed"])).scalar(),
            "stocks_with_yield": len(rows),
            "yield_distribution": distribution,
            "latest_price_date": latest_price_date,
            "industry_avg_yield": [{"industry": name, "avg_yield": value} for name, value in industry_avg],
        }}
    finally:
        session.close()


@router.get("/dividend-summary")
def dividend_summary():
    session = get_session()
    try:
        return {"status": "ok", "data": {
            "total_stocks": session.query(Stock).filter(Stock.status == "active").count(),
            "stocks_with_dividend": session.query(func.count(func.distinct(Dividend.symbol))).filter(Dividend.status.in_(["executed", "confirmed"])).scalar(),
            "total_dividend_records": session.query(Dividend).count(),
        }}
    finally:
        session.close()
