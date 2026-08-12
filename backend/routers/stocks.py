"""股票相关API。"""
from fastapi import APIRouter, Query
from datetime import date
from database.engine import get_session
from database.models import Stock, DailyPrice, Dividend, FinancialStatement
from factor.dividend_yield import calc_all_yields, calc_target_price, get_current_price
from factor.composite_score import calc_composite_score
from factor.dividend_stability import calc_stability_score, get_yearly_dps
from factor.dividend_growth import calc_all_cagrs
from factor.profitability import get_latest_financials, get_financial_trend, assess_cashflow_quality
from factor.debt_risk import get_debt_metrics, assess_debt_risk
from factor.valuation import calc_historical_yield_stats, yield_valuation_zone
from factor.dividend_trap import detect_dividend_trap
from sqlalchemy import func

router = APIRouter()


@router.get("/list")
def list_stocks(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str = Query("symbol"),
    sort_dir: str = Query("asc"),
    search: str = Query(None),
):
    """获取股票列表。"""
    session = get_session()
    try:
        query = session.query(Stock).filter(Stock.status == "active")
        if search:
            query = query.filter(
                (Stock.symbol.contains(search)) | (Stock.name.contains(search))
            )

        total = query.count()

        # 排序
        sort_col = getattr(Stock, sort_by, Stock.symbol)
        if sort_dir == "desc":
            query = query.order_by(sort_col.desc())
        else:
            query = query.order_by(sort_col)

        stocks = query.offset((page - 1) * page_size).limit(page_size).all()

        return {
            "status": "ok",
            "data": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [
                    {
                        "symbol": s.symbol,
                        "name": s.name,
                        "exchange": s.exchange,
                        "industry": s.industry,
                        "market_cap": s.total_market_cap,
                    }
                    for s in stocks
                ],
            },
        }
    finally:
        session.close()


@router.get("/{symbol}")
def get_stock(symbol: str):
    """获取单只股票基本信息+实时行情。"""
    session = get_session()
    try:
        stock = session.query(Stock).filter(Stock.symbol == symbol).first()
        if not stock:
            return {"status": "error", "error": "股票不存在"}

        price = get_current_price(session, symbol)
        yields = calc_all_yields(session, symbol, price)

        return {
            "status": "ok",
            "data": {
                "symbol": stock.symbol,
                "name": stock.name,
                "exchange": stock.exchange,
                "industry": stock.industry,
                "market_cap": stock.total_market_cap,
                "current_price": price,
                "yields": yields,
            },
        }
    finally:
        session.close()


@router.get("/{symbol}/detail")
def get_stock_detail(symbol: str):
    """获取股票完整详情（分红/财务/评分/风险）。"""
    session = get_session()
    try:
        stock = session.query(Stock).filter(Stock.symbol == symbol).first()
        if not stock:
            return {"status": "error", "error": "股票不存在"}

        price = get_current_price(session, symbol)
        yields = calc_all_yields(session, symbol, price)
        stability = calc_stability_score(session, symbol)
        growth = calc_all_cagrs(session, symbol)
        fin = get_latest_financials(session, symbol)
        fin_trend = get_financial_trend(session, symbol, 8)
        cf_quality = assess_cashflow_quality(session, symbol)
        debt = assess_debt_risk(session, symbol)
        trap = detect_dividend_trap(session, symbol, yields.get("ttm_yield"))
        stats = calc_historical_yield_stats(session, symbol, 5)
        zone = yield_valuation_zone(yields.get("ttm_yield"), stats)
        score = calc_composite_score(session, symbol)
        yearly = get_yearly_dps(session, symbol, 10)

        # 历史分红记录
        divs = (
            session.query(Dividend)
            .filter(Dividend.symbol == symbol)
            .order_by(Dividend.ex_date.desc())
            .limit(30)
            .all()
        )

        # 目标股价
        ttm_dps = yields.get("ttm_dps", 0)
        target_prices = calc_target_price(ttm_dps) if ttm_dps else {}

        return {
            "status": "ok",
            "data": {
                "basic": {
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "industry": stock.industry,
                    "market_cap": stock.total_market_cap,
                    "listing_date": str(stock.listing_date) if stock.listing_date else None,
                },
                "price": price,
                "yields": yields,
                "stability": stability,
                "growth": growth,
                "financials": fin,
                "financial_trend": fin_trend,
                "cashflow_quality": cf_quality,
                "debt_risk": debt,
                "trap": trap,
                "valuation_stats": stats,
                "zone": zone,
                "score": score,
                "yearly_dps": yearly,
                "target_prices": target_prices,
                "dividend_history": [
                    {
                        "report_year": d.report_year,
                        "dividend_type": d.dividend_type,
                        "dps": d.cash_div_per_share,
                        "ex_date": str(d.ex_date) if d.ex_date else None,
                        "status": d.status,
                    }
                    for d in divs
                ],
            },
        }
    finally:
        session.close()
