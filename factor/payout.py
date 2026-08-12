"""派息率与FCF覆盖率计算。

公式：
- Payout Ratio = 现金分红总额 / 归母净利润
- FCF Payout = 现金分红总额 / 自由现金流
- FCF Coverage = FCF / 现金分红总额（>1 表示可覆盖）
"""
from datetime import date
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from database.models import Dividend, FinancialStatement, Stock


def calc_payout_ratio(
    total_dividend: float, net_profit: float
) -> Optional[float]:
    """计算派息率(%)。"""
    if not net_profit or net_profit <= 0 or not total_dividend:
        return None
    return round(total_dividend / net_profit * 100, 2)


def calc_fcf_payout(
    total_dividend: float, free_cashflow: float
) -> Optional[float]:
    """计算FCF派息率(%)。"""
    if not free_cashflow or free_cashflow <= 0 or not total_dividend:
        return None
    return round(total_dividend / free_cashflow * 100, 2)


def calc_fcf_coverage(
    free_cashflow: float, total_dividend: float
) -> Optional[float]:
    """计算FCF覆盖率。>1表示FCF可覆盖分红。"""
    if not total_dividend or total_dividend <= 0 or not free_cashflow:
        return None
    return round(free_cashflow / total_dividend, 2)


def get_latest_payout(session: Session, symbol: str) -> dict:
    """获取最新财年的派息率，分子和分母均为公司总额口径。"""
    # 最新分红记录
    latest_div = (
        session.query(Dividend)
        .filter(
            Dividend.symbol == symbol,
            Dividend.report_year <= date.today().year - 1,
            Dividend.status.in_(["executed", "confirmed"]),
            Dividend.cash_div_per_share > 0,
        )
        .order_by(Dividend.ex_date.desc())
        .first()
    )

    if not latest_div:
        return {}

    report_year = latest_div.report_year
    # 优先匹配分红所属财年的年报，避免将季度利润与年度分红混用。
    latest_fin = (
        session.query(FinancialStatement)
        .filter(
            FinancialStatement.symbol == symbol,
            FinancialStatement.net_profit.isnot(None),
            FinancialStatement.report_type == "annual",
            *([extract("year", FinancialStatement.report_date) == report_year] if report_year else []),
        )
        .order_by(FinancialStatement.report_date.desc())
        .first()
    )

    year_divs = session.query(
        func.sum(Dividend.cash_div_per_share),
        func.sum(Dividend.total_cash_dividend),
    ).filter(
        Dividend.symbol == symbol,
        Dividend.report_year == report_year,
        Dividend.status.in_(["executed", "confirmed"]),
        Dividend.cash_div_per_share > 0,
    ).first()
    dps = float(year_divs[0] or 0)
    total_dividend = float(year_divs[1] or 0)
    stock = session.query(Stock).filter(Stock.symbol == symbol).first()
    if total_dividend <= 0 and stock and stock.total_shares and dps > 0:
        total_dividend = dps * float(stock.total_shares)

    result = {
        "dps": dps,
        "total_dividend": total_dividend or None,
        "report_year": report_year,
        "ex_date": str(latest_div.ex_date) if latest_div.ex_date else None,
    }

    if latest_fin:
        result["net_profit"] = latest_fin.net_profit
        result["operating_cf"] = latest_fin.operating_cf
        result["free_cf"] = latest_fin.free_cf
        result["payout_ratio"] = calc_payout_ratio(total_dividend, latest_fin.net_profit)
        result["fcf_payout"] = calc_fcf_payout(total_dividend, latest_fin.free_cf)
        result["fcf_coverage"] = calc_fcf_coverage(latest_fin.free_cf, total_dividend)

    return result
