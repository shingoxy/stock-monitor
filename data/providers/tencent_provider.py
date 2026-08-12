"""腾讯财经 Provider — PE/PB/市值/换手率（不封IP）。

基于 a-stock-data SKILL.md §1.2 腾讯财经 API。
"""
import urllib.request
from datetime import date
from typing import Optional

import pandas as pd
from loguru import logger

from data.provider import DataProvider

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 沪市指数白名单（与深市 000xxx 个股同段）
SH_INDEX = {"000300", "000905", "000016", "000688", "000852", "000010"}


def _get_prefix(code: str) -> str:
    """6位代码 → 市场前缀 sh/sz/bj。"""
    c = code.lower()
    if c.startswith(("sh", "sz", "bj")):
        return c[:2]
    if c.startswith("92"):
        return "bj"
    if c.startswith(("5", "6", "9")):
        return "sh"
    if c.startswith(("4", "8")):
        return "bj"
    if code in SH_INDEX:
        return "sh"
    return "sz"


def tencent_quote_batch(codes: list[str]) -> dict[str, dict]:
    """批量拉取腾讯财经实时行情。返回 {code: {...}} dict。"""
    if not codes:
        return {}

    prefixed = []
    key_of = {}
    for c in codes:
        p = _get_prefix(c)
        full = f"{p}{c}"
        prefixed.append(full)
        key_of[full] = c

    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = resp.read().decode("gbk")
    except Exception as e:
        logger.error(f"腾讯行情请求失败: {e}")
        return {}

    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue

        code = key_of.get(key, key[2:])
        q = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_amt": float(vals[31]) if vals[31] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "float_mcap_yi": float(vals[44]) if vals[44] else 0,
            "mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
        }
        # 僵尸报价检测
        q["is_stale"] = (
            q["amount_wan"] == 0 and q["price"] == q["last_close"] and q["price"] > 0
        )
        result[code] = q

    return result


class TencentProvider(DataProvider):
    """腾讯财经 Provider（实时行情/PE/PB/市值）。"""

    def get_stock_list(self) -> pd.DataFrame:
        raise NotImplementedError("股票列表通过东财获取")

    def get_daily_prices(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        raise NotImplementedError("日线行情通过mootdx获取")

    def get_realtime_quote(self, symbols: list[str]) -> pd.DataFrame:
        data = tencent_quote_batch(symbols)
        if not data:
            return pd.DataFrame()

        rows = []
        for code, q in data.items():
            rows.append({
                "symbol": code,
                "name": q["name"],
                "price": q["price"],
                "last_close": q["last_close"],
                "change_pct": q["change_pct"],
                "pe_ttm": q["pe_ttm"],
                "pb": q["pb"],
                "market_cap": q["mcap_yi"] * 1e8,
                "float_market_cap": q["float_mcap_yi"] * 1e8,
                "turnover_rate": q["turnover_pct"],
                "is_stale": q.get("is_stale", False),
            })
        return pd.DataFrame(rows)

    def get_dividend_history(self, symbol: str) -> list[dict]:
        raise NotImplementedError("分红历史通过东财获取")

    def get_financial_report(self, symbol: str, report_type: str) -> list[dict]:
        raise NotImplementedError("财报通过新浪获取")

    def get_stock_info(self, symbol: str) -> dict:
        raise NotImplementedError("个股信息通过东财获取")
