"""数据批量采集 — 分红/行情/财务数据入库。

支持断点续传，历史数据入库后不重复请求。
"""
import sys
import time
from pathlib import Path
from datetime import date, datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from sqlalchemy import func

from database.engine import get_session, init_db
from database.models import (
    Stock, DailyPrice, Dividend, FinancialStatement, ValuationHistory,
    DataSyncState,
)
from data.providers.eastmoney_provider import get_dividend_history, get_stock_info
from data.providers.sina_provider import (
    sina_financial_report, extract_income_fields,
    extract_balance_fields, extract_cashflow_fields, _safe_float,
)
from data.providers.mootdx_provider import get_kline
from data.providers.tencent_provider import tencent_quote_batch
from config.logging import setup_logging

setup_logging()


def _sync_state(session, dataset: str, symbol: str):
    return session.query(DataSyncState).filter(
        DataSyncState.dataset == dataset, DataSyncState.symbol == symbol
    ).first()


def _mark_sync(session, dataset: str, symbol: str, record_count=None, error=None):
    state = _sync_state(session, dataset, symbol)
    if state is None:
        state = DataSyncState(dataset=dataset, symbol=symbol)
        session.add(state)
    state.last_attempt_at = datetime.utcnow()
    state.last_error = str(error)[:2000] if error else None
    if error is None:
        state.last_success_at = datetime.utcnow()
        state.record_count = int(record_count or 0)


# ── 分红数据采集 ──────────────────────────────────────────

def fetch_dividends(symbols: list[str] = None, batch_size: int = 100, refresh_days: int = 7):
    """批量增量同步分红；近期已刷新股票暂不重复请求。"""
    session = get_session()

    if symbols is None:
        stocks = session.query(Stock).filter(Stock.status == "active").all()
        symbols = [s.symbol for s in stocks]

    logger.info(f"开始采集分红数据，共 {len(symbols)} 只股票")
    fetched = 0
    skipped = 0
    errors = 0

    for i, symbol in enumerate(symbols):
        state = _sync_state(session, "dividends", symbol)
        last_sync = state.last_success_at if state else session.query(
            func.max(Dividend.updated_at)
        ).filter(Dividend.symbol == symbol).scalar()
        if last_sync and last_sync >= datetime.utcnow() - timedelta(days=refresh_days):
            skipped += 1
            continue
        try:
            data = get_dividend_history(symbol, page_size=50)
            if data:
                _save_dividends(session, symbol, data)
                fetched += 1
            else:
                logger.debug(f"{symbol}: 无分红数据")
            _mark_sync(session, "dividends", symbol, len(data))

        except Exception as e:
            errors += 1
            _mark_sync(session, "dividends", symbol, error=e)
            logger.error(f"{symbol} 分红数据获取失败: {e}")

        if (i + 1) % batch_size == 0:
            session.commit()
            logger.info(f"进度: {i + 1}/{len(symbols)} (获取:{fetched} 跳过:{skipped} 错误:{errors})")

    session.commit()
    logger.info(f"分红数据采集完成: 获取 {fetched}, 跳过 {skipped}, 错误 {errors}")
    session.close()


def _save_dividends(session, symbol: str, data: list[dict]):
    """保存分红数据到数据库。"""
    for row in data:
        ex_date = None
        if row.get("date") and row["date"] != "None":
            try:
                ex_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
            except ValueError:
                pass

        plan_date = None
        if row.get("plan_notice_date") and row["plan_notice_date"] != "None":
            try:
                plan_date = datetime.strptime(row["plan_notice_date"], "%Y-%m-%d").date()
            except ValueError:
                pass

        bonus_rmb = row.get("bonus_rmb", 0) or 0
        if bonus_rmb <= 0 and (row.get("bonus_ratio", 0) or 0) <= 0:
            continue  # 无实际分红内容

        status = row.get("status", "proposed")
        if ex_date and ex_date > date.today() and status == "executed":
            status = "confirmed"
        div = session.query(Dividend).filter(
            Dividend.symbol == symbol,
            Dividend.report_year == row.get("report_year"),
            Dividend.dividend_type == row.get("dividend_type", "annual"),
            Dividend.ex_date == ex_date,
            Dividend.cash_div_per_share == bonus_rmb,
        ).first()
        if div is None:
            div = Dividend(symbol=symbol)
            session.add(div)
        div.report_year = row.get("report_year")
        div.dividend_type = row.get("dividend_type", "annual")
        div.board_plan_date = plan_date
        div.ex_date = ex_date
        div.cash_div_per_share = bonus_rmb
        div.cash_div_per_10_shares = row.get("cash_div_per_10_shares") or (bonus_rmb * 10 if bonus_rmb else 0)
        div.bonus_shares_ratio = row.get("bonus_ratio", 0) or 0
        div.transfer_ratio = row.get("transfer_ratio", 0) or 0
        div.total_cash_dividend = row.get("total_dividend")
        div.status = status


# ── 行情数据采集 ──────────────────────────────────────────

def fetch_daily_prices(symbols: list[str] = None, days: int = 2500):
    """批量拉取日线行情入库（mootdx，不封IP）。"""
    session = get_session()

    if symbols is None:
        stocks = session.query(Stock).filter(Stock.status == "active").all()
        symbols = [s.symbol for s in stocks]

    logger.info(f"开始采集日线行情，共 {len(symbols)} 只股票，最近 {days} 个交易日")
    success = 0
    errors = 0

    for i, symbol in enumerate(symbols):
        try:
            df = get_kline(symbol, frequency=9, offset=days)
            if df.empty:
                continue

            # 转换并保存
            _save_daily_prices(session, symbol, df)
            success += 1

        except Exception as e:
            errors += 1
            logger.error(f"{symbol} 行情获取失败: {e}")

        if (i + 1) % 100 == 0:
            session.commit()
            logger.info(f"行情进度: {i + 1}/{len(symbols)} (成功:{success} 错误:{errors})")

    session.commit()
    logger.info(f"日线行情采集完成: 成功 {success}, 错误 {errors}")
    session.close()


def _save_daily_prices(session, symbol: str, df):
    """保存日线数据；同一天重复采集时更新，而不是冻结首个值。"""
    for _, row in df.iterrows():
        dt = row.get("date") or row.get("datetime")
        if dt is None:
            continue
        if hasattr(dt, "date"):
            dt = dt.date()
        elif isinstance(dt, str):
            dt = datetime.strptime(dt[:10], "%Y-%m-%d").date()

        dp = session.query(DailyPrice).filter(
            DailyPrice.symbol == symbol, DailyPrice.date == dt
        ).first()
        if dp is None:
            dp = DailyPrice(symbol=symbol, date=dt)
            session.add(dp)
        dp.open = _safe_float(row.get("open"))
        dp.high = _safe_float(row.get("high"))
        dp.low = _safe_float(row.get("low"))
        dp.close = _safe_float(row.get("close"))
        dp.volume = _safe_float(row.get("volume") or row.get("vol"))
        dp.turnover = _safe_float(row.get("turnover") or row.get("amount"))


# ── 财务数据采集 ──────────────────────────────────────────

def _latest_expected_report_date(today: date = None) -> date:
    today = today or date.today()
    if today.month >= 11:
        return date(today.year, 9, 30)
    if today.month >= 8:
        return date(today.year, 6, 30)
    if today.month >= 5:
        return date(today.year, 3, 31)
    return date(today.year - 1, 12, 31)


def fetch_financials(symbols: list[str] = None, batch_size: int = 50):
    """批量拉取财务报表入库（新浪，低风险）。"""
    session = get_session()

    if symbols is None:
        stocks = session.query(Stock).filter(Stock.status == "active").all()
        symbols = [s.symbol for s in stocks]

    logger.info(f"开始采集财务数据，共 {len(symbols)} 只股票")
    success = 0
    errors = 0
    expected_period = _latest_expected_report_date()

    for i, symbol in enumerate(symbols):
        state = _sync_state(session, "financials", symbol)
        latest_period = session.query(func.max(FinancialStatement.report_date)).filter(
            FinancialStatement.symbol == symbol
        ).scalar()
        if latest_period and latest_period >= expected_period:
            success += 1
            continue
        if state and state.last_success_at and state.last_success_at >= datetime.utcnow() - timedelta(days=7):
            success += 1
            continue
        try:
            # 利润表
            lrb = sina_financial_report(symbol, "lrb", num=12)
            income_data = extract_income_fields(lrb)

            # 资产负债表
            fzb = sina_financial_report(symbol, "fzb", num=12)
            balance_data = extract_balance_fields(fzb)

            # 现金流量表
            llb = sina_financial_report(symbol, "llb", num=12)
            cashflow_data = extract_cashflow_fields(llb)

            # 合并保存
            _save_financials(session, symbol, income_data, balance_data, cashflow_data)
            _mark_sync(session, "financials", symbol, len(income_data))
            success += 1

        except Exception as e:
            errors += 1
            _mark_sync(session, "financials", symbol, error=e)
            logger.error(f"{symbol} 财务数据获取失败: {e}")

        if (i + 1) % batch_size == 0:
            session.commit()
            logger.info(f"财务进度: {i + 1}/{len(symbols)} (成功:{success} 错误:{errors})")

    session.commit()
    logger.info(f"财务数据采集完成: 成功 {success}, 错误 {errors}")
    session.close()


def _save_financials(session, symbol, income_data, balance_data, cashflow_data):
    """合并三表数据并保存。"""
    # 以报告期为key合并
    merged = {}
    for rec in income_data:
        period = rec["report_date"]
        merged[period] = {"report_date": period}
        merged[period].update(rec)

    for rec in balance_data:
        period = rec["report_date"]
        if period not in merged:
            merged[period] = {"report_date": period}
        merged[period].update(rec)

    for rec in cashflow_data:
        period = rec["report_date"]
        if period not in merged:
            merged[period] = {"report_date": period}
        merged[period].update(rec)

    for period, data in merged.items():
        try:
            report_date = datetime.strptime(period, "%Y-%m-%d").date()
        except ValueError:
            continue

        # 推断报告类型
        month = report_date.month
        if month == 3:
            rtype = "Q1"
        elif month == 6:
            rtype = "H1"
        elif month == 9:
            rtype = "Q3"
        else:
            rtype = "annual"

        net_profit = data.get("net_profit")
        operating_cf = data.get("operating_cf")
        total_assets = data.get("total_assets")
        total_liab = data.get("total_liabilities")
        equity = data.get("shareholders_equity")

        # 计算 ROE/ROA
        roe = None
        if net_profit and equity and equity > 0:
            if rtype == "annual":
                roe = round(net_profit / equity * 100, 2)
            else:
                roe = round(net_profit / equity * 100 * (12 / month), 2)

        roa = None
        if net_profit and total_assets and total_assets > 0:
            if rtype == "annual":
                roa = round(net_profit / total_assets * 100, 2)
            else:
                roa = round(net_profit / total_assets * 100 * (12 / month), 2)

        # 投资活动现金流不等于资本开支；来源未提供资本开支时不伪造FCF。
        investing_cf = data.get("investing_cf")
        free_cf = data.get("free_cf")

        # 现金流质量
        ocf_to_ni = None
        if operating_cf and net_profit and net_profit > 0:
            ocf_to_ni = round(operating_cf / net_profit, 2)

        # 计算利润率
        revenue = data.get("revenue")
        gross_margin = None
        net_margin = None
        if net_profit and revenue and revenue > 0:
            net_margin = round(net_profit / revenue * 100, 2)

        operating_profit = data.get("operating_profit")
        operating_margin = None
        if operating_profit and revenue and revenue > 0:
            operating_margin = round(operating_profit / revenue * 100, 2)

        fs = session.query(FinancialStatement).filter(
            FinancialStatement.symbol == symbol,
            FinancialStatement.report_date == report_date,
        ).first()
        if fs is None:
            fs = FinancialStatement(symbol=symbol, report_date=report_date)
            session.add(fs)
        for key, value in {
            "report_type": rtype, "revenue": revenue,
            "revenue_yoy": data.get("revenue_yoy"), "net_profit": net_profit,
            "net_profit_yoy": data.get("net_profit_yoy"), "gross_margin": gross_margin,
            "net_margin": net_margin, "operating_margin": operating_margin,
            "total_assets": total_assets, "total_liabilities": total_liab,
            "shareholders_equity": equity, "debt_ratio": data.get("debt_ratio"),
            "current_ratio": data.get("current_ratio"), "quick_ratio": data.get("quick_ratio"),
            "operating_cf": operating_cf, "investing_cf": investing_cf,
            "financing_cf": data.get("financing_cf"), "free_cf": free_cf,
            "roe": roe, "roa": roa, "ocf_to_net_income": ocf_to_ni,
        }.items():
            if value is not None:
                setattr(fs, key, value)


def fetch_realtime_valuations(symbols: list[str] = None, batch_size: int = 100):
    """同步腾讯行情、PE/PB、市值及当日估值快照。"""
    session = get_session()
    if symbols is None:
        symbols = [s[0] for s in session.query(Stock.symbol).filter(Stock.status == "active").all()]
    today = date.today()
    start = today - timedelta(days=365)
    ttm_rows = session.query(
        Dividend.symbol, func.sum(Dividend.cash_div_per_share)
    ).filter(
        Dividend.status == "executed",
        Dividend.ex_date >= start,
        Dividend.ex_date <= today,
        Dividend.cash_div_per_share > 0,
    ).group_by(Dividend.symbol).all()
    ttm_dps = {symbol: float(dps) for symbol, dps in ttm_rows if dps}

    updated = 0
    for offset in range(0, len(symbols), batch_size):
        quotes = tencent_quote_batch(symbols[offset:offset + batch_size])
        for symbol, quote in quotes.items():
            price = quote.get("price") or 0
            if price <= 0:
                continue
            stock = session.query(Stock).filter(Stock.symbol == symbol).first()
            if stock is None:
                continue
            stock.name = quote.get("name") or stock.name
            stock.total_market_cap = (quote.get("mcap_yi") or 0) * 1e8 or stock.total_market_cap
            stock.float_market_cap = (quote.get("float_mcap_yi") or 0) * 1e8 or stock.float_market_cap
            price_row = session.query(DailyPrice).filter(
                DailyPrice.symbol == symbol, DailyPrice.date == today
            ).first()
            if price_row is None:
                price_row = DailyPrice(symbol=symbol, date=today)
                session.add(price_row)
            price_row.open = quote.get("open")
            price_row.high = quote.get("high")
            price_row.low = quote.get("low")
            price_row.close = price
            price_row.turnover = (quote.get("amount_wan") or 0) * 10000
            price_row.turnover_rate = quote.get("turnover_pct")
            price_row.market_cap = stock.total_market_cap

            val = session.query(ValuationHistory).filter(
                ValuationHistory.symbol == symbol, ValuationHistory.date == today
            ).first()
            if val is None:
                val = ValuationHistory(symbol=symbol, date=today)
                session.add(val)
            val.pe_ttm = quote.get("pe_ttm") or None
            val.pb = quote.get("pb") or None
            if ttm_dps.get(symbol):
                val.dividend_yield_ttm = round(ttm_dps[symbol] / price * 100, 4)
            updated += 1
        session.commit()
        logger.info(f"实时行情/估值进度: {min(offset + batch_size, len(symbols))}/{len(symbols)}")
    session.close()
    logger.info(f"实时行情/估值同步完成: {updated} 只")


# ── 快速测试 ──────────────────────────────────────────────

def test_maotai():
    """测试茅台数据完整性。"""
    session = get_session()
    symbol = "600519"

    # 分红数据
    divs = session.query(Dividend).filter(Dividend.symbol == symbol).order_by(Dividend.ex_date.desc()).all()
    logger.info(f"茅台分红记录: {len(divs)} 条")
    for d in divs[:5]:
        logger.info(f"  {d.report_year} | DPS={d.cash_div_per_share} | 除息日={d.ex_date} | 状态={d.status}")

    # 行情数据
    prices = session.query(DailyPrice).filter(DailyPrice.symbol == symbol).count()
    logger.info(f"茅台行情记录: {prices} 条")

    # 财务数据
    fins = session.query(FinancialStatement).filter(FinancialStatement.symbol == symbol).count()
    logger.info(f"茅台财务记录: {fins} 条")

    session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="A股数据批量采集")
    parser.add_argument("--dividends", action="store_true", help="采集分红数据")
    parser.add_argument("--prices", action="store_true", help="采集行情数据")
    parser.add_argument("--financials", action="store_true", help="采集财务数据")
    parser.add_argument("--valuations", action="store_true", help="采集实时行情与估值")
    parser.add_argument("--all", action="store_true", help="采集全部数据")
    parser.add_argument("--test", action="store_true", help="测试茅台数据")
    parser.add_argument("--symbols", nargs="+", help="指定股票代码")
    parser.add_argument("--symbol-prefix", help="按代码前缀选择股票，例如 000")
    args = parser.parse_args()

    init_db()
    if args.symbol_prefix and not args.symbols:
        session = get_session()
        args.symbols = [row[0] for row in session.query(Stock.symbol).filter(
            Stock.status == "active", Stock.symbol.startswith(args.symbol_prefix)
        ).all()]
        session.close()

    if args.all or args.dividends:
        fetch_dividends(args.symbols)
    if args.all or args.prices:
        fetch_daily_prices(args.symbols)
    if args.all or args.financials:
        fetch_financials(args.symbols)
    if args.all or args.valuations:
        fetch_realtime_valuations(args.symbols)
    if args.test:
        test_maotai()
    if not any([args.dividends, args.prices, args.financials, args.valuations, args.all, args.test]):
        parser.print_help()
