"""估值指标与历史百分位。

PE / PB 历史百分位 + 股息率历史百分位。
"""
import numpy as np
from typing import Optional
from datetime import date, timedelta
from sqlalchemy.orm import Session
from database.models import DailyPrice, Dividend, FinancialStatement


def calc_pe_ttm(price: float, eps_ttm: float) -> Optional[float]:
    """计算PE(TTM)。"""
    if not eps_ttm or eps_ttm <= 0 or not price:
        return None
    return round(price / eps_ttm, 2)


def calc_pb(price: float, bvps: float) -> Optional[float]:
    """计算PB。"""
    if not bvps or bvps <= 0 or not price:
        return None
    return round(price / bvps, 2)


def calc_yield_percentile(
    current_yield: float, historical_yields: list[float]
) -> Optional[float]:
    """计算当前股息率在历史序列中的百分位(0-100)。"""
    if not historical_yields or len(historical_yields) < 5:
        return None
    if current_yield is None:
        return None

    arr = np.array(historical_yields)
    percentile = round(float(np.sum(arr < current_yield) / len(arr) * 100), 1)
    return percentile


def calc_historical_yield_stats(
    session: Session, symbol: str, years: int = 5
) -> dict:
    """计算历史股息率统计（需要先有估值历史数据）。

    这里用分红+行情原始数据计算。
    """
    today = date.today()
    start = today - timedelta(days=years * 365)

    # 获取历史分红
    divs = (
        session.query(Dividend)
        .filter(
            Dividend.symbol == symbol,
            Dividend.status.in_(["executed", "confirmed"]),
            Dividend.cash_div_per_share > 0,
            Dividend.ex_date >= start,
        )
        .order_by(Dividend.ex_date)
        .all()
    )

    if not divs:
        return {}

    # 按年汇总DPS
    yearly_dps = {}
    for d in divs:
        yr = d.report_year
        if yr not in yearly_dps:
            yearly_dps[yr] = {"dps": 0, "ex_date": d.ex_date}
        yearly_dps[yr]["dps"] += d.cash_div_per_share

    # 计算每个除息日的股息率
    yields = []
    for yr, info in yearly_dps.items():
        if not info["ex_date"]:
            continue
        price_row = (
            session.query(DailyPrice.close)
            .filter(DailyPrice.symbol == symbol, DailyPrice.date < info["ex_date"])
            .order_by(DailyPrice.date.desc())
            .first()
        )
        if price_row and price_row[0] > 0:
            y = info["dps"] / price_row[0] * 100
            yields.append(y)

    if not yields:
        return {}

    arr = np.array(yields)
    return {
        "count": len(yields),
        "min": round(float(np.min(arr)), 2),
        "max": round(float(np.max(arr)), 2),
        "mean": round(float(np.mean(arr)), 2),
        "median": round(float(np.median(arr)), 2),
        "p20": round(float(np.percentile(arr, 20)), 2),
        "p50": round(float(np.percentile(arr, 50)), 2),
        "p80": round(float(np.percentile(arr, 80)), 2),
        "p90": round(float(np.percentile(arr, 90)), 2),
    }


def yield_valuation_zone(
    current_yield: float, stats: dict
) -> dict:
    """判断当前股息率所处的估值区间。"""
    if not stats or current_yield is None:
        return {"zone": "unknown", "description": "数据不足"}

    p20 = stats.get("p20", 0)
    p50 = stats.get("p50", 0)
    p80 = stats.get("p80", 0)
    p90 = stats.get("p90", 0)

    if current_yield >= p90:
        zone = "extreme_high"
        description = f"当前股息率{current_yield:.2f}%位于历史极高区间(>P90={p90:.2f}%)"
    elif current_yield >= p80:
        zone = "high"
        description = f"当前股息率{current_yield:.2f}%位于历史高区间(P80-P90)"
    elif current_yield >= p50:
        zone = "normal_high"
        description = f"当前股息率{current_yield:.2f}%位于正常偏高区间(P50-P80)"
    elif current_yield >= p20:
        zone = "normal_low"
        description = f"当前股息率{current_yield:.2f}%位于正常偏低区间(P20-P50)"
    else:
        zone = "low"
        description = f"当前股息率{current_yield:.2f}%位于历史低区间(<P20={p20:.2f}%)"

    return {"zone": zone, "description": description}
