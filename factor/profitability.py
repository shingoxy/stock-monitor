"""盈利能力指标计算。

ROE / ROA / 毛利率 / 净利率 / 营业利润率 / 现金流质量
"""
from typing import Optional
from sqlalchemy.orm import Session
from database.models import FinancialStatement


def get_latest_financials(session: Session, symbol: str) -> dict:
    """获取最新财务指标。"""
    fin = (
        session.query(FinancialStatement)
        .filter(FinancialStatement.symbol == symbol)
        .order_by(FinancialStatement.report_date.desc())
        .first()
    )
    if not fin:
        return {}

    return {
        "report_date": str(fin.report_date) if fin.report_date else None,
        "report_type": fin.report_type,
        "revenue": fin.revenue,
        "net_profit": fin.net_profit,
        "roe": fin.roe,
        "roa": fin.roa,
        "gross_margin": fin.gross_margin,
        "net_margin": fin.net_margin,
        "operating_margin": fin.operating_margin,
        "operating_cf": fin.operating_cf,
        "free_cf": fin.free_cf,
        "ocf_to_net_income": fin.ocf_to_net_income,
        "revenue_yoy": fin.revenue_yoy,
        "net_profit_yoy": fin.net_profit_yoy,
    }


def get_financial_trend(session: Session, symbol: str, periods: int = 8) -> list[dict]:
    """获取财务趋势数据（多期）。"""
    rows = (
        session.query(FinancialStatement)
        .filter(FinancialStatement.symbol == symbol)
        .order_by(FinancialStatement.report_date.desc())
        .limit(periods)
        .all()
    )
    return [
        {
            "report_date": str(r.report_date),
            "report_type": r.report_type,
            "revenue": r.revenue,
            "net_profit": r.net_profit,
            "roe": r.roe,
            "operating_cf": r.operating_cf,
            "free_cf": r.free_cf,
        }
        for r in rows
    ]


def assess_cashflow_quality(session: Session, symbol: str) -> dict:
    """评估现金流质量。"""
    rows = (
        session.query(FinancialStatement)
        .filter(
            FinancialStatement.symbol == symbol,
            FinancialStatement.operating_cf.isnot(None),
            FinancialStatement.net_profit.isnot(None),
        )
        .order_by(FinancialStatement.report_date.desc())
        .limit(8)
        .all()
    )

    if not rows:
        return {"quality": "unknown", "reason": "数据不足"}

    # 检查OCF/NI比率
    ratios = []
    for r in rows:
        if r.net_profit and r.net_profit > 0 and r.operating_cf:
            ratios.append(r.operating_cf / r.net_profit)

    if not ratios:
        return {"quality": "unknown", "reason": "数据不足"}

    avg_ratio = sum(ratios) / len(ratios)

    if avg_ratio >= 1.0:
        quality = "good"
        reason = f"经营现金流/净利润均值={avg_ratio:.2f}，利润质量高"
    elif avg_ratio >= 0.7:
        quality = "normal"
        reason = f"经营现金流/净利润均值={avg_ratio:.2f}，基本正常"
    elif avg_ratio >= 0.3:
        quality = "warning"
        reason = f"经营现金流/净利润均值={avg_ratio:.2f}，现金流质量偏低"
    else:
        quality = "poor"
        reason = f"经营现金流/净利润均值={avg_ratio:.2f}，利润可能含金量低"

    return {"quality": quality, "reason": reason, "avg_ratio": round(avg_ratio, 2)}
