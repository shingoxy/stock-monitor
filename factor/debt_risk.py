"""资产负债风险评估。

重点识别：高分红 + 高负债 的潜在不可持续情况。
"""
from typing import Optional
from sqlalchemy.orm import Session
from database.models import FinancialStatement


def get_debt_metrics(session: Session, symbol: str) -> dict:
    """获取资产负债指标。"""
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
        "debt_ratio": fin.debt_ratio,
        "current_ratio": fin.current_ratio,
        "quick_ratio": fin.quick_ratio,
        "total_assets": fin.total_assets,
        "total_liabilities": fin.total_liabilities,
        "shareholders_equity": fin.shareholders_equity,
    }


def assess_debt_risk(session: Session, symbol: str) -> dict:
    """评估债务风险等级。

    Returns:
        {risk_level, reasons}
    """
    metrics = get_debt_metrics(session, symbol)
    if not metrics:
        return {"risk_level": "unknown", "reasons": ["数据不足"]}

    risk_score = 0
    reasons = []

    debt_ratio = metrics.get("debt_ratio")
    current_ratio = metrics.get("current_ratio")
    quick_ratio = metrics.get("quick_ratio")

    # 资产负债率
    if debt_ratio is not None:
        if debt_ratio > 80:
            risk_score += 3
            reasons.append(f"资产负债率{debt_ratio:.1f}%极高")
        elif debt_ratio > 65:
            risk_score += 2
            reasons.append(f"资产负债率{debt_ratio:.1f}%偏高")
        elif debt_ratio > 50:
            risk_score += 1
            reasons.append(f"资产负债率{debt_ratio:.1f}%中等")
        else:
            reasons.append(f"资产负债率{debt_ratio:.1f}%正常")

    # 流动比率
    if current_ratio is not None:
        if current_ratio < 1.0:
            risk_score += 2
            reasons.append(f"流动比率{current_ratio:.2f}偏低")
        elif current_ratio < 1.5:
            risk_score += 1
            reasons.append(f"流动比率{current_ratio:.2f}偏紧")

    # 速动比率
    if quick_ratio is not None:
        if quick_ratio < 0.5:
            risk_score += 1
            reasons.append(f"速动比率{quick_ratio:.2f}偏低")

    if risk_score >= 4:
        level = "high"
    elif risk_score >= 2:
        level = "medium"
    else:
        level = "low"

    return {"risk_level": level, "risk_score": risk_score, "reasons": reasons}
