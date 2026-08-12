"""东财 Provider — 分红/资金面/个股信息（需限流）。

基于 a-stock-data SKILL.md §4.4(分红) §6.3(个股信息)。
所有东财请求走 em_get() 串行限流防封。
"""
import time
import random
import json
import urllib.request
import urllib.parse
from datetime import date, datetime
from typing import Optional

from loguru import logger

from config.settings import settings

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# 不使用系统代理（macOS 可能配置了本地代理导致 requests 连接失败）
_PROXY_HANDLER = urllib.request.ProxyHandler({})
_OPENER = urllib.request.build_opener(_PROXY_HANDLER)

_em_last_call = [0.0]


def em_get(url: str, params: dict = None, headers: dict = None, timeout: int = 15) -> dict:
    """东财统一请求入口：自动节流 + 不走系统代理。返回 JSON dict。"""
    wait = settings.em_min_interval - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))

    if params:
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}"
    else:
        full_url = url

    req = urllib.request.Request(full_url)
    req.add_header("User-Agent", UA)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        resp = _OPENER.open(req, timeout=timeout)
        data = resp.read().decode("utf-8")
        return json.loads(data)
    finally:
        _em_last_call[0] = time.time()


def em_get_raw(url: str, params: dict = None, headers: dict = None, timeout: int = 15) -> str:
    """东财请求入口，返回原始文本。"""
    wait = settings.em_min_interval - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))

    if params:
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}"
    else:
        full_url = url

    req = urllib.request.Request(full_url)
    req.add_header("User-Agent", UA)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        resp = _OPENER.open(req, timeout=timeout)
        return resp.read().decode("utf-8")
    finally:
        _em_last_call[0] = time.time()


def eastmoney_datacenter(
    report_name: str,
    columns: str = "ALL",
    filter_str: str = "",
    page_size: int = 50,
    sort_columns: str = "",
    sort_types: str = "-1",
    strict: bool = False,
) -> list[dict]:
    """东财数据中心统一查询。"""
    params = {
        "reportName": report_name,
        "columns": columns,
        "filter": filter_str,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": sort_columns,
        "sortTypes": sort_types,
        "source": "WEB",
        "client": "WEB",
    }
    try:
        d = em_get(DATACENTER_URL, params=params, timeout=15)
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
    except Exception as e:
        logger.error(f"东财数据中心查询失败 [{report_name}]: {e}")
        if strict:
            raise
    return []


def get_dividend_history(code: str, page_size: int = 50) -> list[dict]:
    """分红送转历史。

    返回: [{date, bonus_rmb(每股派息), transfer_ratio(转增), bonus_ratio(送股),
            plan(进度), report_year, ex_date, total_dividend}]
    """
    data = eastmoney_datacenter(
        "RPT_SHAREBONUS_DET",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size,
        sort_columns="EX_DIVIDEND_DATE",
        sort_types="-1",
        strict=True,
    )
    rows = []
    for row in data:
        ex_date = str(row.get("EX_DIVIDEND_DATE", ""))[:10]
        # API返回的是每10股派息，转换为每股派息
        bonus_per_10 = row.get("PRETAX_BONUS_RMB", 0) or 0
        bonus_rmb = bonus_per_10 / 10.0 if bonus_per_10 else 0

        # 推断报告年度
        report_year_str = str(row.get("REPORT_YEAR", ""))
        if report_year_str and report_year_str != "None":
            try:
                report_year = int(report_year_str[:4])
            except (ValueError, TypeError):
                report_year = None
        else:
            report_year = None

        # 如果REPORT_YEAR为空，从除息日推断
        if report_year is None and ex_date and ex_date != "None":
            try:
                ex_year = int(ex_date[:4])
                # 除息日通常在报告期之后半年内
                # 例如2025年除息通常对应2024年年报
                report_year = ex_year - 1
            except (ValueError, TypeError):
                pass

        # 确定分红类型
        plan_date = str(row.get("PLAN_NOTICE_DATE", ""))[:10]
        assign_type = str(row.get("ASSIGN_TYPE", ""))
        if "中期" in assign_type or "半年" in assign_type:
            div_type = "interim"
        elif "特别" in assign_type:
            div_type = "special"
        else:
            div_type = "annual"

        # 进度映射
        progress = str(row.get("ASSIGN_PROGRESS", ""))
        if "实施" in progress:
            status = "executed"
        elif "通过" in progress or "股东大会" in progress:
            status = "approved"
        elif "预案" in progress or "分配方案" in progress:
            status = "proposed"
        else:
            status = "proposed"

        rows.append({
            "date": ex_date,
            "bonus_rmb": bonus_rmb,
            "cash_div_per_10_shares": bonus_per_10,
            "transfer_ratio": row.get("TRANSFER_RATIO", 0) or 0,
            "bonus_ratio": row.get("BONUS_RATIO", 0) or 0,
            "plan": progress,
            "report_year": report_year,
            "dividend_type": div_type,
            "status": status,
            "plan_notice_date": plan_date,
            "total_dividend": row.get("TOTAL_BONUS_RMB", 0),
        })
    return rows


def get_stock_info(code: str) -> dict:
    """东财个股基本面信息。"""
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43",
        "secid": f"{market_code}.{code}",
    }
    try:
        d = em_get(url, params=params, timeout=10)
        data = d.get("data", {})
        return {
            "code": data.get("f57", ""),
            "name": data.get("f58", ""),
            "industry": data.get("f127", ""),
            "total_shares": data.get("f84", 0),
            "float_shares": data.get("f85", 0),
            "mcap": data.get("f116", 0),
            "float_mcap": data.get("f117", 0),
            "list_date": str(data.get("f189", "")),
            "price": data.get("f43", 0),
        }
    except Exception as e:
        logger.error(f"东财个股信息获取失败 [{code}]: {e}")
        return {}


def get_stock_list_from_push2() -> list[dict]:
    """从东财push2获取全量A股列表。分页拉取，含行业/市值。"""
    all_stocks = []
    page = 1
    page_size = 100  # API 实际最大返回 100 条/页

    while True:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": str(page),
            "pz": str(page_size),
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f2,f3,f12,f14,f20,f21,f23,f26,f100,f115",
        }
        try:
            d = em_get(url, params=params, timeout=15)
            data = d.get("data", {})
            if not data or not data.get("diff"):
                break
            items = data["diff"]
        except Exception as e:
            logger.error(f"东财股票列表第{page}页获取失败: {e}")
            break

        for item in items:
            code = str(item.get("f12", ""))
            name = item.get("f14", "")

            # 跳过ST/退市
            if not code or not name:
                continue
            if "ST" in name.upper() or "退" in name:
                continue

            # 判断交易所
            if code.startswith("6"):
                exchange = "SH"
            elif code.startswith(("0", "3")):
                exchange = "SZ"
            elif code.startswith(("4", "8", "92")):
                exchange = "BJ"
            else:
                exchange = "SZ"

            # 北交所可选跳过
            if exchange == "BJ" and not settings.include_bj_exchange:
                continue

            all_stocks.append({
                "symbol": code,
                "name": name,
                "exchange": exchange,
                "industry": item.get("f100", ""),
                "total_market_cap": item.get("f20", 0) or 0,
                "float_market_cap": item.get("f21", 0) or 0,
                "pb": item.get("f23", 0) or 0,
                "listing_date_raw": item.get("f26", ""),
                "price": item.get("f2", 0) or 0,
            })

        if len(items) < page_size:
            break
        page += 1

    return all_stocks
