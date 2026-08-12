"""数据缓存层 — 避免重复请求历史数据。

历史财务/分红数据一旦入库，优先从数据库读取。
"""
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session

from database.models import DailyPrice, Dividend, FinancialStatement, Stock


def get_cached_daily_prices(
    session: Session, symbol: str, start_date: date, end_date: date
) -> pd.DataFrame:
    """从数据库获取已缓存的日线行情。"""
    rows = (
        session.query(DailyPrice)
        .filter(
            DailyPrice.symbol == symbol,
            DailyPrice.date >= start_date,
            DailyPrice.date <= end_date,
        )
        .order_by(DailyPrice.date)
        .all()
    )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([
        {
            "date": r.date, "open": r.open, "high": r.high,
            "low": r.low, "close": r.close, "volume": r.volume,
            "turnover": r.turnover,
        }
        for r in rows
    ])


def get_latest_price_date(session: Session, symbol: str) -> Optional[date]:
    """获取某只股票最新的行情日期。"""
    result = (
        session.query(DailyPrice.date)
        .filter(DailyPrice.symbol == symbol)
        .order_by(DailyPrice.date.desc())
        .first()
    )
    return result[0] if result else None


def get_cached_dividends(session: Session, symbol: str) -> list[dict]:
    """从数据库获取已缓存的分红数据。"""
    rows = (
        session.query(Dividend)
        .filter(Dividend.symbol == symbol)
        .order_by(Dividend.ex_date.desc())
        .all()
    )
    if not rows:
        return []
    return [
        {
            "report_year": r.report_year,
            "dividend_type": r.dividend_type,
            "cash_div_per_share": r.cash_div_per_share,
            "cash_div_per_10_shares": r.cash_div_per_10_shares,
            "bonus_shares_ratio": r.bonus_shares_ratio,
            "transfer_ratio": r.transfer_ratio,
            "ex_date": r.ex_date,
            "payment_date": r.payment_date,
            "status": r.status,
            "total_cash_dividend": r.total_cash_dividend,
            "net_profit": r.net_profit,
            "payout_ratio": r.payout_ratio,
        }
        for r in rows
    ]


def has_dividend_data(session: Session, symbol: str) -> bool:
    """检查是否已有分红数据。"""
    count = (
        session.query(Dividend)
        .filter(Dividend.symbol == symbol)
        .count()
    )
    return count > 0


def get_cached_financials(
    session: Session, symbol: str, report_type: str = None
) -> pd.DataFrame:
    """从数据库获取已缓存的财务数据。"""
    query = session.query(FinancialStatement).filter(
        FinancialStatement.symbol == symbol
    )
    if report_type:
        query = query.filter(FinancialStatement.report_type == report_type)
    rows = query.order_by(FinancialStatement.report_date.desc()).all()

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([
        {k: v for k, v in r.__dict__.items() if not k.startswith("_")}
        for r in rows
    ])
