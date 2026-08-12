"""Tests that exercise production factor and aggregation code."""
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.services.high_dividend import build_high_dividend_snapshot
from database.models import Base, DailyPrice, Dividend, FinancialStatement, Stock
from factor.dividend_yield import calc_ttm_dps
from factor.payout import get_latest_payout


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed_company(session):
    today = date.today()
    session.add(Stock(
        symbol="600001", name="示例股份", exchange="SH", status="active",
        total_shares=1_000_000_000, total_market_cap=10_000_000_000,
    ))
    session.add(DailyPrice(symbol="600001", date=today, close=10.0))
    session.add_all([
        Dividend(
            symbol="600001", report_year=today.year - 1, dividend_type="annual",
            ex_date=today - timedelta(days=30), cash_div_per_share=0.5, status="executed",
        ),
        Dividend(
            symbol="600001", report_year=today.year, dividend_type="interim",
            ex_date=today + timedelta(days=10), cash_div_per_share=1.0, status="executed",
        ),
    ])
    session.add(FinancialStatement(
        symbol="600001", report_date=date(today.year - 1, 12, 31), report_type="annual",
        net_profit=1_000_000_000, free_cf=1_250_000_000, eps=1.0, roe=12.0,
    ))
    session.commit()


def test_ttm_excludes_future_ex_date():
    session = make_session()
    seed_company(session)
    assert calc_ttm_dps(session, "600001") == 0.5


def test_payout_uses_company_total_amounts():
    session = make_session()
    seed_company(session)
    result = get_latest_payout(session, "600001")
    assert result["total_dividend"] == 500_000_000
    assert result["payout_ratio"] == 50.0
    assert result["fcf_coverage"] == 2.5


def test_snapshot_has_card_fields_and_excludes_future_dividend():
    session = make_session()
    seed_company(session)
    row = build_high_dividend_snapshot(session)[0]
    assert row["symbol"] == "600001"
    assert row["ttm_dps"] == 0.5
    assert row["this_year_dps"] == 0.5
    assert row["ttm_yield"] == 5.0
    assert row["pe_ttm"] == 10.0
