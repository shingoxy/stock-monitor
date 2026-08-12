"""综合高股息评分系统。

7维评分（0-100）：
- 股息率: 25%
- 分红稳定性: 20%
- 股息增长: 10%
- 派息可持续性: 15%
- 现金流: 10%
- 财务质量: 10%
- 估值: 10%

所有评分可追溯来源。
"""
from typing import Optional
from sqlalchemy.orm import Session

from factor.dividend_yield import calc_all_yields, get_current_price, calc_yield
from factor.dividend_stability import calc_stability_score
from factor.dividend_growth import calc_all_cagrs
from factor.payout import get_latest_payout
from factor.profitability import get_latest_financials, assess_cashflow_quality
from factor.valuation import calc_historical_yield_stats, yield_valuation_zone
from factor.debt_risk import assess_debt_risk
from factor.dividend_trap import detect_dividend_trap


DEFAULT_WEIGHTS = {
    "yield": 0.25,
    "stability": 0.20,
    "growth": 0.10,
    "payout": 0.15,
    "cashflow": 0.10,
    "quality": 0.10,
    "valuation": 0.10,
}


def _score_yield(ttm_yield: float) -> float:
    """股息率评分(0-100)。"""
    if ttm_yield is None or ttm_yield <= 0:
        return 0
    if ttm_yield >= 10:
        return 100
    if ttm_yield >= 8:
        return 90
    if ttm_yield >= 6:
        return 80
    if ttm_yield >= 5:
        return 70
    if ttm_yield >= 4:
        return 60
    if ttm_yield >= 3:
        return 50
    if ttm_yield >= 2:
        return 35
    return max(0, ttm_yield * 10)


def _score_payout(payout_ratio: float, fcf_coverage: float) -> Optional[float]:
    """派息可持续性评分(0-100)。"""
    if payout_ratio is None and fcf_coverage is None:
        return None
    score = 50  # 基准分

    if payout_ratio is not None:
        if 30 <= payout_ratio <= 60:
            score += 30
        elif 60 < payout_ratio <= 80:
            score += 20
        elif 80 < payout_ratio <= 100:
            score += 10
        elif payout_ratio > 100:
            score -= 20

    if fcf_coverage is not None:
        if fcf_coverage >= 1.5:
            score += 20
        elif fcf_coverage >= 1.0:
            score += 10
        elif fcf_coverage < 0.5:
            score -= 20

    return max(0, min(100, score))


def _score_cashflow(quality: dict) -> Optional[float]:
    """现金流评分(0-100)。"""
    q = quality.get("quality", "unknown")
    if q == "good":
        return 90
    if q == "normal":
        return 70
    if q == "warning":
        return 40
    if q == "poor":
        return 20
    return None


def _score_quality(debt_risk: dict, fin: dict) -> Optional[float]:
    """财务质量评分(0-100)。"""
    if not debt_risk or not fin:
        return None
    score = 50

    level = debt_risk.get("risk_level", "unknown")
    if level == "low":
        score += 30
    elif level == "medium":
        score += 10
    elif level == "high":
        score -= 20

    roe = fin.get("roe")
    if roe and roe > 15:
        score += 20
    elif roe and roe > 10:
        score += 10
    elif roe and roe < 5:
        score -= 10

    return max(0, min(100, score))


def _score_valuation(zone_info: dict) -> Optional[float]:
    """估值评分(0-100)。越高表示越低估（越有投资价值）。"""
    zone = zone_info.get("zone", "unknown")
    scores = {
        "extreme_high": 95,
        "high": 80,
        "normal_high": 60,
        "normal_low": 40,
        "low": 20,
    }
    return scores.get(zone)


def calc_composite_score(
    session: Session, symbol: str, weights: dict = None
) -> dict:
    """计算综合评分。

    Returns:
        {
            symbol, date, current_price,
            yield_score, stability_score, growth_score, payout_score,
            cashflow_score, quality_score, valuation_score,
            composite_score, dividend_trap_risk,
            yields, stability, growth, payout, cashflow_quality,
            debt_risk, trap, valuation_stats, zone,
            weights
        }
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    price = get_current_price(session, symbol)
    if not price:
        return {"symbol": symbol, "error": "no_price"}

    # 1. 股息率
    yields = calc_all_yields(session, symbol, price)
    ttm_yield = yields.get("ttm_yield")
    yield_score = _score_yield(ttm_yield)

    # 2. 稳定性
    stability = calc_stability_score(session, symbol)
    stability_score = stability.get("score", 0)

    # 3. 增长
    growth = calc_all_cagrs(session, symbol)
    cagr_5y = growth.get("cagr_5y")
    growth_score = None
    if cagr_5y is not None:
        if cagr_5y >= 10:
            growth_score = 90
        elif cagr_5y >= 5:
            growth_score = 75
        elif cagr_5y >= 0:
            growth_score = 55
        else:
            growth_score = 25

    # 4. 派息可持续性
    payout = get_latest_payout(session, symbol)
    payout_score = _score_score(
        payout.get("payout_ratio"),
        payout.get("fcf_coverage"),
    )

    # 5. 现金流
    cf_quality = assess_cashflow_quality(session, symbol)
    cashflow_score = _score_cashflow(cf_quality)

    # 6. 财务质量
    debt_risk = assess_debt_risk(session, symbol)
    fin = get_latest_financials(session, symbol)
    quality_score = _score_quality(debt_risk, fin)

    # 7. 估值
    stats = calc_historical_yield_stats(session, symbol, years=5)
    zone_info = yield_valuation_zone(ttm_yield, stats)
    valuation_score = _score_valuation(zone_info)

    # 陷阱检测
    trap = detect_dividend_trap(session, symbol, ttm_yield)

    # 综合分
    dimension_scores = {
        "yield": yield_score,
        "stability": stability_score,
        "growth": growth_score,
        "payout": payout_score,
        "cashflow": cashflow_score,
        "quality": quality_score,
        "valuation": valuation_score,
    }
    available_weight = sum(weights[name] for name, value in dimension_scores.items() if value is not None)
    composite = None
    if available_weight:
        composite = round(
            sum(value * weights[name] for name, value in dimension_scores.items() if value is not None)
            / available_weight,
            1,
        )

    return {
        "symbol": symbol,
        "current_price": price,
        "ttm_yield": ttm_yield,
        "yield_score": round(yield_score, 1),
        "stability_score": round(stability_score, 1),
        "growth_score": round(growth_score, 1) if growth_score is not None else None,
        "payout_score": round(payout_score, 1) if payout_score is not None else None,
        "cashflow_score": round(cashflow_score, 1) if cashflow_score is not None else None,
        "quality_score": round(quality_score, 1) if quality_score is not None else None,
        "valuation_score": round(valuation_score, 1) if valuation_score is not None else None,
        "composite_score": composite,
        "score_coverage": round(available_weight * 100, 1),
        "dividend_trap_risk": trap["risk_level"],
        "yields": yields,
        "stability": stability,
        "growth": growth,
        "payout": payout,
        "cashflow_quality": cf_quality,
        "debt_risk": debt_risk,
        "trap": trap,
        "valuation_stats": stats,
        "zone": zone_info,
        "weights": weights,
    }


def _score_score(payout_ratio, fcf_coverage):
    return _score_payout(payout_ratio, fcf_coverage)
