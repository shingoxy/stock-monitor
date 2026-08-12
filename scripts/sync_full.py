"""Canonical full-data synchronization entry point.

Primary sources are structured Eastmoney, Tencent, Sina and mootdx providers.
No credential-bearing natural-language MCP response is used for core records.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from database.engine import init_db
from scripts.data_fetcher import (
    fetch_daily_prices,
    fetch_dividends,
    fetch_financials,
    fetch_realtime_valuations,
)
from scripts.seed_stocks import seed_stocks


def main():
    parser = argparse.ArgumentParser(description="同步股票、分红、财务、行情和估值数据")
    parser.add_argument("--symbols", nargs="+", help="仅同步指定股票")
    parser.add_argument("--with-history", action="store_true", help="同步历史日线（耗时较长）")
    parser.add_argument("--skip-stock-list", action="store_true", help="跳过股票主数据刷新")
    parser.add_argument("--history-days", type=int, default=2500)
    args = parser.parse_args()

    init_db()
    if not args.skip_stock_list and not args.symbols:
        seed_stocks()
    # 先刷新卡片直接依赖的价格和估值，长耗时基本面同步随后执行。
    fetch_realtime_valuations(args.symbols)
    fetch_dividends(args.symbols)
    fetch_financials(args.symbols)
    if args.with_history:
        fetch_daily_prices(args.symbols, days=args.history_days)
    logger.info("全量同步完成")


if __name__ == "__main__":
    main()
