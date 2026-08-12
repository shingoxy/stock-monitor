"""High-dividend screener API."""
from fastapi import APIRouter, Query

from backend.services.high_dividend import build_high_dividend_snapshot
from database.engine import get_session

router = APIRouter()


@router.get("/run")
def run_screener(
    min_yield: float = Query(5, ge=0, description="最低股息率(%)"),
    min_years: int = Query(5, ge=0, description="最低连续分红年数"),
    min_roe: float = Query(10, description="最低ROE(%)"),
    min_mcap: float = Query(100e8, ge=0, description="最低市值(元)"),
    max_pe: float = Query(1000, gt=0, description="最高市盈率"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    session = get_session()
    try:
        rows = []
        for row in build_high_dividend_snapshot(session):
            if row["ttm_yield"] < min_yield or row["consecutive_years"] < min_years:
                continue
            if row.get("roe") is None or row["roe"] < min_roe:
                continue
            if row.get("market_cap") is None or row["market_cap"] < min_mcap:
                continue
            if row.get("pe_ttm") is not None and row["pe_ttm"] > max_pe:
                continue
            rows.append(row)

        rows.sort(key=lambda row: row["ttm_yield"], reverse=True)
        start = (page - 1) * page_size
        return {
            "status": "ok",
            "data": {
                "total": len(rows),
                "page": page,
                "page_size": page_size,
                "items": rows[start:start + page_size],
            },
        }
    finally:
        session.close()


@router.get("/presets")
def get_preset_strategies():
    return {"status": "ok", "data": [
        {"name": "高股息蓝筹", "description": "Yield>=5%, 连续分红>=5年, ROE>=10%, 市值>=500亿", "params": {"min_yield": 5, "min_years": 5, "min_roe": 10, "min_mcap": 500e8}},
        {"name": "稳定高股息", "description": "Yield>=4%, 连续分红>=10年", "params": {"min_yield": 4, "min_years": 10, "min_roe": 0, "min_mcap": 0}},
        {"name": "高股息成长", "description": "Yield>=3%, 连续分红>=3年", "params": {"min_yield": 3, "min_years": 3, "min_roe": 0, "min_mcap": 0}},
        {"name": "现金奶牛", "description": "ROE>=12%, Yield>=4%", "params": {"min_yield": 4, "min_years": 0, "min_roe": 12, "min_mcap": 0}},
    ]}
