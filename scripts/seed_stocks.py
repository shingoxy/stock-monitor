"""导入全量A股列表到数据库。

数据源：东财 push2 API（含行业/市值，零鉴权）。
如果 push2 不可用，回退到腾讯行情批量获取。
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from database.engine import get_session, init_db
from database.models import Stock
from data.providers.eastmoney_provider import get_stock_list_from_push2
from data.providers.tencent_provider import tencent_quote_batch
from config.logging import setup_logging

setup_logging()


def seed_stocks():
    """拉取全量A股列表并入库。"""
    logger.info("开始获取A股列表...")

    # 尝试从东财获取
    stocks = get_stock_list_from_push2()

    if not stocks:
        logger.warning("东财 push2 API 不可用，尝试使用腾讯行情批量获取...")
        stocks = _get_stocks_from_tencent()

    logger.info(f"获取到 {len(stocks)} 只股票")

    if not stocks:
        logger.error("未获取到任何股票数据，请检查网络连接")
        return

    session = get_session()
    added = 0
    updated = 0

    try:
        for s in stocks:
            symbol = s["symbol"]
            existing = session.query(Stock).filter(Stock.symbol == symbol).first()

            # 解析上市日期
            list_date = None
            raw = s.get("listing_date_raw", "")
            if raw and len(str(raw)) == 8:
                try:
                    list_date = datetime.strptime(str(raw), "%Y%m%d").date()
                except ValueError:
                    pass

            if existing:
                existing.name = s["name"]
                existing.exchange = s["exchange"]
                existing.industry = s.get("industry", "")
                existing.total_market_cap = s.get("total_market_cap", 0)
                existing.float_market_cap = s.get("float_market_cap", 0)
                if list_date:
                    existing.listing_date = list_date
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                stock = Stock(
                    symbol=symbol,
                    name=s["name"],
                    exchange=s["exchange"],
                    industry=s.get("industry", ""),
                    listing_date=list_date,
                    status="active",
                    total_market_cap=s.get("total_market_cap", 0),
                    float_market_cap=s.get("float_market_cap", 0),
                )
                session.add(stock)
                added += 1

            if (added + updated) % 500 == 0:
                session.commit()
                logger.info(f"已处理 {added + updated} 只...")

        session.commit()
        logger.info(f"股票列表导入完成: 新增 {added}, 更新 {updated}, 总计 {added + updated}")

    except Exception as e:
        session.rollback()
        logger.error(f"导入失败: {e}")
        raise
    finally:
        session.close()


def _get_stocks_from_tencent() -> list[dict]:
    """使用腾讯行情批量获取股票列表（回退方案）。

    生成主要A股代码范围，通过腾讯API验证哪些代码有效。
    """
    # 生成主要A股代码范围
    codes = []

    # 上海主板: 600000-603999, 605000-605999
    for i in range(600000, 604000):
        codes.append(str(i))
    for i in range(605000, 606000):
        codes.append(str(i))

    # 上海科创板: 688000-689999
    for i in range(688000, 690000):
        codes.append(str(i))

    # 深圳主板: 000001-000999
    for i in range(1, 1000):
        codes.append(f"{i:06d}")

    # 深圳中小板: 002000-002999
    for i in range(2000, 3000):
        codes.append(f"{i:06d}")

    # 深圳创业板: 300000-301999
    for i in range(300000, 302000):
        codes.append(str(i))

    logger.info(f"生成 {len(codes)} 个候选代码，开始批量验证...")

    # 批量获取（每批50个）
    stocks = []
    batch_size = 50
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        try:
            results = tencent_quote_batch(batch)
            for code, q in results.items():
                if q.get("price", 0) > 0 and not q.get("is_stale", False):
                    name = q.get("name", "")
                    if not name or "ST" in name.upper() or "退" in name:
                        continue

                    if code.startswith("6"):
                        exchange = "SH"
                    elif code.startswith(("0", "3")):
                        exchange = "SZ"
                    else:
                        exchange = "SZ"

                    stocks.append({
                        "symbol": code,
                        "name": name,
                        "exchange": exchange,
                        "industry": "",
                        "total_market_cap": q.get("mcap_yi", 0) * 1e8,
                        "float_market_cap": q.get("float_mcap_yi", 0) * 1e8,
                        "listing_date_raw": "",
                        "price": q.get("price", 0),
                    })
        except Exception as e:
            logger.debug(f"批量获取失败: {e}")

        if (i + batch_size) % 1000 == 0:
            logger.info(f"已验证 {i + batch_size}/{len(codes)} 个代码，找到 {len(stocks)} 只有效股票")

    return stocks


if __name__ == "__main__":
    init_db()
    seed_stocks()
