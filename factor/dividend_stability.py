"""分红稳定性评分。

评分维度：
- 连续分红年数
- 分红波动率（DPS标准差/均值）
- 股息增长率（CAGR）
- 取消分红次数
- 股息下降次数
"""
import math
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from database.models import Dividend


def get_yearly_dps(session: Session, symbol: str, years: int = 10) -> dict:
    """获取年度DPS汇总。"""
    from datetime import date
    start_year = date.today().year - years
    rows = (
        session.query(
            Dividend.report_year,
            func.coalesce(func.sum(Dividend.cash_div_per_share), 0).label("total_dps"),
        )
        .filter(
            Dividend.symbol == symbol,
            Dividend.report_year >= start_year,
            Dividend.status.in_(["executed", "confirmed"]),
            Dividend.cash_div_per_share > 0,
        )
        .group_by(Dividend.report_year)
        .order_by(Dividend.report_year)
        .all()
    )
    return {r.report_year: float(r.total_dps) for r in rows if r.report_year}


def calc_consecutive_years(session: Session, symbol: str) -> int:
    """计算连续分红年数（从最近有分红的年份往前）。"""
    yearly = get_yearly_dps(session, symbol, years=20)
    if not yearly:
        return 0

    # 找到最近有分红的年份
    max_year = max(yearly.keys())
    consecutive = 0
    for yr in range(max_year, max_year - 20, -1):
        if yr in yearly and yearly[yr] > 0:
            consecutive += 1
        else:
            break
    return consecutive


def calc_dividend_cv(session: Session, symbol: str, years: int = 10) -> Optional[float]:
    """计算分红变异系数（标准差/均值）。"""
    yearly = get_yearly_dps(session, symbol, years)
    values = [v for v in yearly.values() if v > 0]
    if len(values) < 3:
        return None

    mean = sum(values) / len(values)
    if mean == 0:
        return None
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std = math.sqrt(variance)
    return round(std / mean, 4)


def calc_dividend_decline_count(session: Session, symbol: str, years: int = 10) -> int:
    """计算分红下降次数。"""
    yearly = get_yearly_dps(session, symbol, years)
    sorted_years = sorted(yearly.keys())
    declines = 0
    for i in range(1, len(sorted_years)):
        if yearly[sorted_years[i]] < yearly[sorted_years[i - 1]]:
            declines += 1
    return declines


def calc_stability_score(session: Session, symbol: str) -> dict:
    """计算分红稳定性综合评分。

    Returns:
        {score, grade, consecutive_years, cv, decline_count, reasons}
    """
    consecutive = calc_consecutive_years(session, symbol)
    cv = calc_dividend_cv(session, symbol)
    declines = calc_dividend_decline_count(session, symbol)
    yearly = get_yearly_dps(session, symbol, 10)
    active_years = len([v for v in yearly.values() if v > 0])

    score = 0
    reasons = []

    # 连续分红年数（最高30分）
    if consecutive >= 15:
        score += 30
        reasons.append(f"连续分红{consecutive}年(优秀)")
    elif consecutive >= 10:
        score += 25
        reasons.append(f"连续分红{consecutive}年(良好)")
    elif consecutive >= 5:
        score += 18
        reasons.append(f"连续分红{consecutive}年")
    elif consecutive >= 3:
        score += 10
        reasons.append(f"连续分红{consecutive}年(较短)")
    else:
        score += 5
        reasons.append(f"连续分红{consecutive}年(不稳定)")

    # 分红稳定性（变异系数，最高30分）
    if cv is not None:
        if cv < 0.15:
            score += 30
            reasons.append(f"分红波动极小(CV={cv:.2f})")
        elif cv < 0.3:
            score += 22
            reasons.append(f"分红波动较小(CV={cv:.2f})")
        elif cv < 0.5:
            score += 15
            reasons.append(f"分红波动中等(CV={cv:.2f})")
        else:
            score += 5
            reasons.append(f"分红波动较大(CV={cv:.2f})")
    else:
        score += 5
        reasons.append("数据不足无法计算波动")

    # 分红下降次数（最高20分）
    if declines == 0:
        score += 20
        reasons.append("近10年无分红下降")
    elif declines <= 1:
        score += 15
        reasons.append(f"近10年分红下降{declines}次")
    elif declines <= 3:
        score += 8
        reasons.append(f"近10年分红下降{declines}次")
    else:
        score += 2
        reasons.append(f"近10年分红下降{declines}次(频繁)")

    # 活跃年份（最高20分）
    if active_years >= 10:
        score += 20
        reasons.append(f"近10年有{active_years}年分红")
    elif active_years >= 7:
        score += 15
        reasons.append(f"近10年有{active_years}年分红")
    elif active_years >= 5:
        score += 10
        reasons.append(f"近10年有{active_years}年分红")
    else:
        score += 3
        reasons.append(f"近10年仅{active_years}年分红")

    # 评级
    if score >= 85:
        grade = "S"
    elif score >= 70:
        grade = "A"
    elif score >= 55:
        grade = "B"
    elif score >= 40:
        grade = "C"
    else:
        grade = "D"

    return {
        "score": min(score, 100),
        "grade": grade,
        "consecutive_years": consecutive,
        "cv": cv,
        "decline_count": declines,
        "active_years": active_years,
        "reasons": reasons,
    }
