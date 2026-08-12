"""mootdx Provider — K线/财务快照/F10（TCP，不封IP）。

基于 a-stock-data SKILL.md §1.1。
"""
import socket
from datetime import date, datetime
from typing import Optional

import pandas as pd
from loguru import logger

from data.provider import DataProvider

# 实测可用的通达信服务器（按延迟排序，2026-06 验证）
_TDX_SERVERS = [
    ('119.97.185.59', 7709), ('124.70.133.119', 7709), ('116.205.183.150', 7709),
    ('123.60.73.44', 7709),  ('116.205.163.254', 7709), ('121.36.225.169', 7709),
    ('123.60.70.228', 7709), ('124.71.9.153', 7709),    ('110.41.147.114', 7709),
    ('124.71.187.122', 7709),
]

_client = None


def _probe(ip: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def get_tdx_client(market: str = 'std'):
    """创建 mootdx 客户端，规避 BESTIP bug + 坏服务器验活。"""
    from mootdx.quotes import Quotes

    global _client
    if _client is not None:
        return _client

    for ip, port in _TDX_SERVERS:
        if not _probe(ip, port):
            continue
        try:
            c = Quotes.factory(market=market, server=(ip, port))
            # 真实取数验活
            df = c.bars(symbol='000001', frequency=9, offset=1)
            if df is not None and not df.empty:
                _client = c
                return c
        except Exception:
            continue

    # fallback: bestip 测速
    for kwargs in ({'bestip': True}, {}):
        try:
            c = Quotes.factory(market=market, **kwargs)
            df = c.bars(symbol='000001', frequency=9, offset=1)
            if df is not None and not df.empty:
                _client = c
                return c
        except Exception:
            continue

    raise RuntimeError("所有 mootdx 服务器均无法取到数据")


def get_kline(
    symbol: str,
    frequency: int = 9,
    offset: int = 250,
) -> pd.DataFrame:
    """获取K线数据。

    frequency: 0=5分钟 1=15分 2=30分 3=60分 4=日线 5=周线 6=月线 9=日线
    offset: 取最近N根
    """
    client = get_tdx_client()
    try:
        df = client.bars(symbol=symbol, frequency=frequency, offset=offset)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.error(f"mootdx K线获取失败 [{symbol}]: {e}")
    return pd.DataFrame()


def get_finance_snapshot(symbol: str) -> Optional[dict]:
    """获取财务快照（37字段季报数据）。"""
    client = get_tdx_client()
    try:
        fin = client.finance(symbol=symbol)
        if fin is not None and not fin.empty:
            return fin.to_dict('records')[0] if hasattr(fin, 'to_dict') else fin
    except Exception as e:
        logger.error(f"mootdx 财务快照获取失败 [{symbol}]: {e}")
    return None


class MootdxProvider(DataProvider):
    """mootdx Provider（K线/财务/F10）。"""

    def get_stock_list(self) -> pd.DataFrame:
        raise NotImplementedError("股票列表通过东财获取")

    def get_daily_prices(
        self, symbol: str, start_date: date, end_date: date
    ) -> pd.DataFrame:
        df = get_kline(symbol, frequency=9, offset=5000)
        if df.empty:
            return df

        # mootdx 返回的 datetime 列需要转换
        if 'datetime' in df.columns:
            df['date'] = pd.to_datetime(df['datetime']).dt.date
        elif 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date']).dt.date

        # 筛选日期范围
        if 'date' in df.columns:
            df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]

        # 标准化列名
        col_map = {
            'open': 'open', 'close': 'close', 'high': 'high', 'low': 'low',
            'vol': 'volume', 'amount': 'turnover',
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        return df

    def get_realtime_quote(self, symbols: list[str]) -> pd.DataFrame:
        raise NotImplementedError("实时行情通过腾讯获取")

    def get_dividend_history(self, symbol: str) -> list[dict]:
        raise NotImplementedError("分红历史通过东财获取")

    def get_financial_report(self, symbol: str, report_type: str) -> list[dict]:
        raise NotImplementedError("财报通过新浪获取")

    def get_stock_info(self, symbol: str) -> dict:
        raise NotImplementedError("个股信息通过东财获取")
