"""新浪财经 Provider — 财报三表（资产负债表/利润表/现金流量表）。

基于 a-stock-data SKILL.md §6.4。
"""
from datetime import date
from typing import Optional

import json
import urllib.request
import urllib.parse
from loguru import logger

from data.provider import DataProvider

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 不使用系统代理
_PROXY_HANDLER = urllib.request.ProxyHandler({})
_OPENER = urllib.request.build_opener(_PROXY_HANDLER)


def sina_financial_report(
    code: str, report_type: str = "lrb", num: int = 20
) -> list[dict]:
    """新浪财报三表。

    Args:
        code: 6位代码
        report_type: "fzb"(资产负债表) / "lrb"(利润表) / "llb"(现金流量表)
        num: 取最近N期

    Returns:
        按报告期倒序的记录列表
    """
    prefix = "sh" if code.startswith("6") else "sz"
    paper_code = f"{prefix}{code}"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code,
        "source": report_type,
        "type": "0",
        "page": "1",
        "num": str(num),
    }
    try:
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}"
        req = urllib.request.Request(full_url)
        req.add_header("User-Agent", UA)
        resp = _OPENER.open(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        report_list = data.get("result", {}).get("data", {}).get("report_list", {}) or {}
    except Exception as e:
        logger.error(f"新浪财报获取失败 [{code} {report_type}]: {e}")
        return []

    rows = []
    for period in sorted(report_list.keys(), reverse=True)[:num]:
        obj = report_list[period]
        rec = {"报告期": f"{period[:4]}-{period[4:6]}-{period[6:8]}"}
        for it in obj.get("data", []) or []:
            title = it.get("item_title", "")
            if not title or it.get("item_value") is None:
                continue
            rec[title] = it.get("item_value")
            tongbi = it.get("item_tongbi")
            if tongbi not in (None, ""):
                rec[title + "_同比"] = tongbi
        rows.append(rec)
    return rows


def extract_income_fields(records: list[dict]) -> list[dict]:
    """从新浪利润表提取关键字段。"""
    result = []
    for rec in records:
        period = rec.get("报告期", "")
        result.append({
            "report_date": period,
            "revenue": _safe_float(rec.get("营业总收入") or rec.get("一、营业总收入")),
            "revenue_yoy": _safe_float(rec.get("营业总收入_同比")),
            "net_profit": _safe_float(rec.get("净利润") or rec.get("归属于母公司所有者的净利润")),
            "net_profit_yoy": _safe_float(rec.get("净利润_同比")),
            "operating_profit": _safe_float(rec.get("营业利润") or rec.get("三、营业利润")),
        })
    return result


def extract_balance_fields(records: list[dict]) -> list[dict]:
    """从新浪资产负债表提取关键字段。"""
    result = []
    for rec in records:
        period = rec.get("报告期", "")
        total_assets = _safe_float(rec.get("资产总计") or rec.get("资产合计"))
        total_liab = _safe_float(rec.get("负债合计") or rec.get("负债总计"))
        equity = _safe_float(rec.get("所有者权益合计") or rec.get("归属于母公司股东权益合计"))

        debt_ratio = None
        if total_assets and total_assets > 0 and total_liab is not None:
            debt_ratio = round(total_liab / total_assets * 100, 2)

        result.append({
            "report_date": period,
            "total_assets": total_assets,
            "total_liabilities": total_liab,
            "shareholders_equity": equity,
            "debt_ratio": debt_ratio,
            "current_ratio": _safe_float(rec.get("流动比率")),
            "quick_ratio": _safe_float(rec.get("速动比率")),
        })
    return result


def extract_cashflow_fields(records: list[dict]) -> list[dict]:
    """从新浪现金流量表提取关键字段。"""
    result = []
    for rec in records:
        period = rec.get("报告期", "")
        result.append({
            "report_date": period,
            "operating_cf": _safe_float(
                rec.get("经营活动产生的现金流量净额")
                or rec.get("经营活动现金流量净额")
            ),
            "investing_cf": _safe_float(
                rec.get("投资活动产生的现金流量净额")
                or rec.get("投资活动现金流量净额")
            ),
            "financing_cf": _safe_float(
                rec.get("筹资活动产生的现金流量净额")
                or rec.get("筹资活动现金流量净额")
            ),
        })
    return result


def _safe_float(val) -> Optional[float]:
    """安全转换为 float，处理逗号、百分号等。"""
    if val is None or val == "" or val == "--":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").replace("%", "").strip()
    if not s or s == "--":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None
