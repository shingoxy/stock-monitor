"""Audit and repair rows created by the legacy importers.

Dry-run is the default. ``--apply`` first creates a consistent SQLite backup.
"""
import argparse
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_, or_, text

from config.settings import settings
from database.engine import get_session
from database.models import Dividend, FinancialStatement, Stock

SH_INDEX_CODES = {"000010", "000016", "000300", "000688", "000852", "000905"}


def sqlite_path() -> Path:
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix):
        raise RuntimeError("自动备份仅支持 SQLite；其他数据库请使用数据库原生备份")
    return Path(settings.database_url[len(prefix):]).resolve()


def create_backup(source: Path) -> Path:
    backup_dir = source.parent / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"{source.stem}_before_repair_{stamp}.db"
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(target)) as dst:
        src.backup(dst)
    return target


def invalid_period_filter():
    return or_(
        and_(FinancialStatement.report_type == "annual", FinancialStatement.report_date.notlike("%-12-31")),
        and_(FinancialStatement.report_type == "Q1", FinancialStatement.report_date.notlike("%-03-31")),
        and_(FinancialStatement.report_type == "H1", FinancialStatement.report_date.notlike("%-06-30")),
        and_(FinancialStatement.report_type == "Q3", FinancialStatement.report_date.notlike("%-09-30")),
    )


def audit(session) -> dict:
    return {
        "invalid_financial_periods": session.query(FinancialStatement).filter(invalid_period_filter()).count(),
        "future_executed_dividends": session.query(Dividend).filter(
            Dividend.status == "executed", Dividend.ex_date > date.today()
        ).count(),
        "untraceable_free_cf": session.query(FinancialStatement).filter(
            FinancialStatement.free_cf.isnot(None)
        ).count(),
        "index_rows_marked_active": session.query(Stock).filter(
            Stock.symbol.in_(SH_INDEX_CODES), Stock.status == "active"
        ).count(),
    }


def repair(apply: bool = False):
    session = get_session()
    before = audit(session)
    print("before", before)
    if not apply:
        session.close()
        print("dry-run only; pass --apply to repair")
        return

    backup = create_backup(sqlite_path())
    try:
        session.query(FinancialStatement).filter(invalid_period_filter()).delete(synchronize_session=False)
        session.query(Dividend).filter(
            Dividend.status == "executed", Dividend.ex_date > date.today()
        ).update({Dividend.status: "confirmed"}, synchronize_session=False)
        session.query(FinancialStatement).filter(
            FinancialStatement.free_cf.isnot(None)
        ).update({FinancialStatement.free_cf: None}, synchronize_session=False)
        session.query(Stock).filter(
            Stock.symbol.in_(SH_INDEX_CODES), Stock.status == "active"
        ).update({Stock.status: "excluded"}, synchronize_session=False)
        session.commit()
        session.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_financials_symbol_date "
            "ON financial_statements(symbol, report_date)"
        ))
        session.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_dividends_identity "
            "ON dividends(symbol, report_year, dividend_type, ex_date, cash_div_per_share)"
        ))
        session.commit()
    except Exception:
        session.rollback()
        raise
    after = audit(session)
    session.close()
    print("backup", backup)
    print("after", after)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    repair(parser.parse_args().apply)
