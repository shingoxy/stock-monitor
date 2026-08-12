"""DataProvider 抽象接口。

所有数据源实现此接口，支持 Primary / Fallback 切换。
"""
from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd
from datetime import date


class DataProvider(ABC):
    """数据源抽象基类。"""

    @abstractmethod
    def get_stock_list(self) -> pd.DataFrame:
        """获取全量股票列表。

        Returns:
            DataFrame: columns=[symbol, name, exchange, industry, listing_date, status]
        """
        ...

    @abstractmethod
    def get_daily_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """获取日线行情。

        Returns:
            DataFrame: columns=[date, open, high, low, close, volume, turnover]
        """
        ...

    @abstractmethod
    def get_realtime_quote(self, symbols: list[str]) -> pd.DataFrame:
        """获取实时行情快照。

        Returns:
            DataFrame: columns=[symbol, name, price, change_pct, pe_ttm, pb,
                                market_cap, float_market_cap, turnover_rate]
        """
        ...

    @abstractmethod
    def get_dividend_history(self, symbol: str) -> list[dict]:
        """获取分红历史。

        Returns:
            list[dict]: 每条包含 date, bonus_rmb(每股派息),
                        transfer_ratio, bonus_ratio, plan(进度)
        """
        ...

    @abstractmethod
    def get_financial_report(
        self, symbol: str, report_type: str
    ) -> list[dict]:
        """获取财务报表。

        Args:
            symbol: 6位股票代码
            report_type: "lrb"(利润表) / "fzb"(资产负债表) / "llb"(现金流量表)

        Returns:
            list[dict]: 按报告期倒序的记录
        """
        ...

    @abstractmethod
    def get_stock_info(self, symbol: str) -> dict:
        """获取个股基本面信息。

        Returns:
            dict: {code, name, industry, total_shares, float_shares,
                    mcap, float_mcap, list_date, price}
        """
        ...
