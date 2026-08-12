"""高股息陷阱检测器。

10条规则：
1. 股价暴跌导致股息率异常升高
2. 盈利连续下降但仍维持高分红
3. FCF无法覆盖分红
4. 派息率超过100%
5. 高负债情况下大额分红
6. 一次性特别分红造成股息率虚高
7. 周期行业处于盈利峰值
8. 资产出售产生一次性利润并分红
9. 公司基本面明显恶化
10. 未来资本开支明显增加

输出：LOW / MEDIUM / HIGH / EXTREME
"""
from sqlalchemy.orm import Session
from datetime import date, timedelta

from database.models import Dividend, FinancialStatement, DailyPrice
from factor.debt_risk import get_debt_metrics
from factor.payout import get_latest_payout


def detect_dividend_trap(session: Session, symbol: str, current_yield: float = None) -> dict:
    """检测高股息陷阱。

    Returns:
        {risk_level, triggered_rules, details}
    """
    triggered = []
    details = []

    today = date.today()
    latest_fin = (
        session.query(FinancialStatement)
        .filter(FinancialStatement.symbol == symbol)
        .order_by(FinancialStatement.report_date.desc())
        .first()
    )

    if latest_fin:
        if latest_fin.net_profit is not None and latest_fin.net_profit < 0:
            triggered.append("R9")
            details.append("公司亏损但仍分红")

        payout = get_latest_payout(session, symbol)
        payout_ratio = payout.get("payout_ratio")
        if payout_ratio is not None and payout_ratio > 100:
            triggered.append("R4")
            details.append(f"派息率{payout_ratio:.1f}%超过100%")

        coverage = payout.get("fcf_coverage")
        if coverage is not None and coverage < 1.0:
            triggered.append("R3")
            details.append(f"FCF覆盖率{coverage:.2f}，无法覆盖分红")

        # 规则5: 高负债+高分红
        debt = get_debt_metrics(session, symbol)
        if (
            debt.get("debt_ratio") is not None
            and debt["debt_ratio"] > 70
            and ((payout_ratio is not None and payout_ratio > 70) or (current_yield or 0) >= 6)
        ):
            triggered.append("R5")
            details.append(f"资产负债率{debt['debt_ratio']:.1f}%且分红水平偏高")

        # 规则9: 基本面恶化
        if latest_fin.net_profit_yoy is not None and latest_fin.net_profit_yoy < -30:
            if "R9" not in triggered:
                triggered.append("R9")
            details.append(f"净利润同比下降{abs(latest_fin.net_profit_yoy):.1f}%")

        # 规则7: 盈利可能处于异常高位
        if (
            latest_fin.net_profit_yoy is not None
            and latest_fin.net_profit_yoy > 50
            and latest_fin.roe is not None
            and latest_fin.roe > 20
        ):
            triggered.append("R7")
            details.append("净利润高速增长且ROE处于高位，需核实周期峰值")

        # 规则8: 利润与经营现金流显著背离
        if (
            latest_fin.net_profit is not None
            and latest_fin.net_profit > 0
            and latest_fin.operating_cf is not None
            and latest_fin.operating_cf <= 0
        ):
            triggered.append("R8")
            details.append("盈利为正但经营现金流为负，需核实一次性利润")

        # 规则10: 投资现金流出显著超过经营现金流
        if (
            latest_fin.investing_cf is not None
            and latest_fin.investing_cf < 0
            and latest_fin.operating_cf is not None
            and latest_fin.operating_cf > 0
            and abs(latest_fin.investing_cf) > latest_fin.operating_cf * 1.5
        ):
            triggered.append("R10")
            details.append("投资现金流出显著超过经营现金流，资本开支压力较高")

        # 规则2: 盈利连续下降
        fins = (
            session.query(FinancialStatement)
            .filter(
                FinancialStatement.symbol == symbol,
                FinancialStatement.net_profit_yoy.isnot(None),
            )
            .order_by(FinancialStatement.report_date.desc())
            .limit(4)
            .all()
        )
        if len(fins) >= 3:
            all_declining = all(f.net_profit_yoy < 0 for f in fins[:3])
            if all_declining:
                triggered.append("R2")
                details.append("净利润连续3期下降")

    # 规则6: 特别分红导致虚高
    special_divs = (
        session.query(Dividend)
        .filter(
            Dividend.symbol == symbol,
            Dividend.dividend_type == "special",
            Dividend.status.in_(["executed", "confirmed"]),
            Dividend.ex_date >= today - timedelta(days=365),
            Dividend.ex_date <= today,
        )
        .count()
    )
    if special_divs > 0:
        triggered.append("R6")
        details.append(f"存在{special_divs}次特别分红")

    # 规则1: 股价明显回撤且股息率异常偏高
    prices = session.query(DailyPrice.close).filter(
        DailyPrice.symbol == symbol,
        DailyPrice.date >= today - timedelta(days=365),
        DailyPrice.date <= today,
        DailyPrice.close > 0,
    ).order_by(DailyPrice.date).all()
    if prices and current_yield is not None:
        high = max(float(p[0]) for p in prices)
        current = float(prices[-1][0])
        drawdown = (current / high - 1) * 100 if high else 0
        if drawdown <= -30 and current_yield >= 6:
            triggered.append("R1")
            details.append(f"近一年股价回撤{abs(drawdown):.1f}%且股息率偏高")

    # 去重，确保一个规则只计一次。
    triggered = list(dict.fromkeys(triggered))

    # 风险等级
    if len(triggered) >= 4:
        risk_level = "EXTREME"
    elif len(triggered) >= 3:
        risk_level = "HIGH"
    elif len(triggered) >= 1:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "risk_level": risk_level,
        "triggered_count": len(triggered),
        "triggered_rules": triggered,
        "details": details,
    }
