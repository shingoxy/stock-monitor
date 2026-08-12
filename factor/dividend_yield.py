"""股息率计算 — TTM / Annual / Forward / Proposed。

公式：
- TTM Yield = 过去12个月实际DPS之和 / 当前股价
- Annual Yield = 最近完整财年DPS / 当前股价
- Forward Yield = 已公告未派DPS / 当前股价（status>=confirmed）
- Proposed Yield = 董事会预案DPS / 当前股价（status=proposed）
"""
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from database.models import Dividend, DailyPrice


def calc_ttm_dps(session: Session, symbol: str, ref_date: date = None) -> Optional[float]:
    """计算过去12个月实际每股分红之和。"""
    if ref_date is None:
        ref_date = date.today()
    start = ref_date - timedelta(days=365)

    rows = (
        session.query(func.coalesce(func.sum(Dividend.cash_div_per_share), 0))
        .filter(
            Dividend.symbol == symbol,
            Dividend.status == "executed",
            Dividend.ex_date >= start,
            Dividend.ex_date <= ref_date,
            Dividend.cash_div_per_share > 0,
        )
        .scalar()
    )
    return float(rows) if rows else 0.0


def calc_annual_dps(session: Session, symbol: str, year: int = None) -> Optional[float]:
    """计算某一年度的年度DPS（含中期+年度汇总）。"""
    if year is None:
        year = date.today().year - 1  # 默认最近完整财年

    rows = (
        session.query(func.coalesce(func.sum(Dividend.cash_div_per_share), 0))
        .filter(
            Dividend.symbol == symbol,
            Dividend.report_year == year,
            Dividend.status.in_(["executed", "confirmed"]),
            Dividend.cash_div_per_share > 0,
        )
        .scalar()
    )
    return float(rows) if rows else 0.0


def calc_forward_dps(session: Session, symbol: str) -> Optional[float]:
    """已公告但未派发的DPS（status=confirmed）。"""
    rows = (
        session.query(func.coalesce(func.sum(Dividend.cash_div_per_share), 0))
        .filter(
            Dividend.symbol == symbol,
            Dividend.status == "confirmed",
            Dividend.cash_div_per_share > 0,
        )
        .scalar()
    )
    return float(rows) if rows else 0.0


def calc_proposed_dps(session: Session, symbol: str) -> Optional[float]:
    """董事会预案DPS（status=proposed）。"""
    rows = (
        session.query(func.coalesce(func.sum(Dividend.cash_div_per_share), 0))
        .filter(
            Dividend.symbol == symbol,
            Dividend.status == "proposed",
            Dividend.cash_div_per_share > 0,
        )
        .scalar()
    )
    return float(rows) if rows else 0.0


def get_current_price(session: Session, symbol: str) -> Optional[float]:
    """获取当前价格；数据库快照超过5天时先尝试刷新。"""
    row = (
        session.query(DailyPrice.date, DailyPrice.close)
        .filter(DailyPrice.symbol == symbol)
        .order_by(DailyPrice.date.desc())
        .first()
    )
    if row and row[1] and (date.today() - row[0]).days <= 5:
        return float(row[1])

    # 从腾讯API获取实时价格
    try:
        from data.providers.tencent_provider import tencent_quote_batch
        quotes = tencent_quote_batch([symbol])
        if symbol in quotes:
            price = quotes[symbol].get("price", 0)
            if price and price > 0:
                return float(price)
    except Exception:
        pass

    # 外部行情不可用时允许使用旧快照，但调用方应同时展示数据日期。
    return float(row[1]) if row and row[1] else None


def calc_yield(dps: float, price: float) -> Optional[float]:
    """计算股息率(%)。"""
    if not price or price <= 0 or not dps:
        return None
    return round(dps / price * 100, 4)


def calc_all_yields(session: Session, symbol: str, price: float = None) -> dict:
    """计算所有口径的股息率。

    Returns:
        {ttm_dps, annual_dps, forward_dps, proposed_dps,
         ttm_yield, annual_yield, forward_yield, proposed_yield}
    """
    if price is None:
        price = get_current_price(session, symbol)
    if not price or price <= 0:
        return {"error": "no_price"}

    ttm_dps = calc_ttm_dps(session, symbol)
    year = date.today().year - 1
    annual_dps = calc_annual_dps(session, symbol, year)
    forward_dps = calc_forward_dps(session, symbol)
    proposed_dps = calc_proposed_dps(session, symbol)

    return {
        "current_price": price,
        "ttm_dps": ttm_dps,
        "annual_dps": annual_dps,
        "forward_dps": forward_dps,
        "proposed_dps": proposed_dps,
        "ttm_yield": calc_yield(ttm_dps, price),
        "annual_yield": calc_yield(annual_dps, price),
        "forward_yield": calc_yield(forward_dps, price),
        "proposed_yield": calc_yield(proposed_dps, price),
    }


def calc_target_price(dps: float, target_yields: list[float] = None) -> dict:
    """根据目标股息率反推股价。"""
    if target_yields is None:
        target_yields = [3, 4, 5, 6, 7, 8, 9, 10]
    if not dps or dps <= 0:
        return {}
    return {f"{y}%": round(dps / (y / 100), 2) for y in target_yields}


def calc_historical_yield_series(
    session: Session, symbol: str, years: int = 10
) -> list[dict]:
    """计算历史股息率序列（基于除息日股价）。

    Returns:
        [{year, dps, ex_date_price, ex_date_yield}]
    """
    today = date.today()
    start_year = today.year - years

    divs = (
        session.query(Dividend)
        .filter(
            Dividend.symbol == symbol,
            Dividend.status.in_(["executed", "confirmed"]),
            Dividend.report_year >= start_year,
            Dividend.cash_div_per_share > 0,
        )
        .order_by(Dividend.report_year)
        .all()
    )

    # 按年汇总DPS
    yearly = {}
    for d in divs:
        yr = d.report_year
        if yr not in yearly:
            yearly[yr] = {"dps": 0, "ex_dates": []}
        yearly[yr]["dps"] += d.cash_div_per_share
        if d.ex_date:
            yearly[yr]["ex_dates"].append(d.ex_date)

    results = []
    for yr in sorted(yearly.keys()):
        dps = yearly[yr]["dps"]
        # 取第一个除息日的前一交易日价格
        ex_dates = sorted(yearly[yr]["ex_dates"])
        ex_price = None
        for ed in ex_dates:
            row = (
                session.query(DailyPrice.close)
                .filter(DailyPrice.symbol == symbol, DailyPrice.date < ed)
                .order_by(DailyPrice.date.desc())
                .first()
            )
            if row and row[0]:
                ex_price = float(row[0])
                break

        yield_pct = calc_yield(dps, ex_price) if ex_price else None
        results.append({
            "year": yr,
            "dps": round(dps, 4),
            "ex_date_price": ex_price,
            "ex_date_yield": yield_pct,
        })

    return results
