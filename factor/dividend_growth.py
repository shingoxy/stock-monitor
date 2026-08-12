"""股息增长率计算。

计算 3Y / 5Y / 10Y 的 Dividend CAGR。
"""
from typing import Optional
from sqlalchemy.orm import Session
from factor.dividend_stability import get_yearly_dps


def calc_dividend_cagr(
    yearly_dps: dict, end_year: int, years: int
) -> Optional[float]:
    """计算股息CAGR。

    Args:
        yearly_dps: {year: dps} dict
        end_year: 结束年份
        years: 回溯年数

    Returns:
        CAGR (小数)，如 0.05 = 5%
    """
    start_year = end_year - years
    end_dps = yearly_dps.get(end_year, 0)
    start_dps = yearly_dps.get(start_year, 0)

    if not start_dps or start_dps <= 0 or not end_dps or end_dps <= 0:
        return None

    if years <= 0:
        return None

    cagr = (end_dps / start_dps) ** (1 / years) - 1
    return round(cagr, 4)


def calc_all_cagrs(session: Session, symbol: str) -> dict:
    """计算3Y/5Y/10Y的股息CAGR。"""
    from datetime import date
    current_year = date.today().year - 1  # 用最近完整财年

    yearly = get_yearly_dps(session, symbol, years=15)

    cagr_3y = calc_dividend_cagr(yearly, current_year, 3)
    cagr_5y = calc_dividend_cagr(yearly, current_year, 5)
    cagr_10y = calc_dividend_cagr(yearly, current_year, 10)

    return {
        "cagr_3y": round(cagr_3y * 100, 2) if cagr_3y is not None else None,
        "cagr_5y": round(cagr_5y * 100, 2) if cagr_5y is not None else None,
        "cagr_10y": round(cagr_10y * 100, 2) if cagr_10y is not None else None,
    }
