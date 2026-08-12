from datetime import date, datetime
from sqlalchemy import (
    Column, String, Float, Integer, Date, DateTime, Boolean,
    ForeignKey, Index, Text, Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


# ── 枚举类型 ──────────────────────────────────────────────

class Exchange(str, enum.Enum):
    SH = "SH"  # 上海
    SZ = "SZ"  # 深圳
    BJ = "BJ"  # 北交所


class StockStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELISTED = "delisted"
    ST = "st"


class DividendType(str, enum.Enum):
    ANNUAL = "annual"        # 年度分红
    INTERIM = "interim"      # 中期分红
    QUARTERLY = "quarterly"  # 季度分红
    SPECIAL = "special"      # 特别分红
    OTHER = "other"          # 其他


class DividendStatus(str, enum.Enum):
    PROPOSED = "proposed"      # 董事会预案
    APPROVED = "approved"      # 股东大会通过
    CONFIRMED = "confirmed"    # 正式公告确认
    EXECUTED = "executed"      # 已派发


# ── 股票基本信息 ──────────────────────────────────────────

class Stock(Base):
    __tablename__ = "stocks"

    symbol = Column(String(10), primary_key=True, comment="股票代码(如600519)")
    name = Column(String(50), nullable=False, comment="公司名称")
    exchange = Column(String(5), nullable=False, comment="交易所: SH/SZ/BJ")
    industry = Column(String(50), comment="行业分类")
    listing_date = Column(Date, comment="上市日期")
    status = Column(String(10), default="active", comment="状态: active/suspended/delisted/st")
    total_shares = Column(Float, comment="总股本(股)")
    float_shares = Column(Float, comment="流通股本(股)")
    total_market_cap = Column(Float, comment="总市值(元)")
    float_market_cap = Column(Float, comment="流通市值(元)")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    dividends = relationship("Dividend", back_populates="stock", lazy="dynamic")
    daily_prices = relationship("DailyPrice", back_populates="stock", lazy="dynamic")
    financial_statements = relationship("FinancialStatement", back_populates="stock", lazy="dynamic")

    def __repr__(self):
        return f"<Stock {self.symbol} {self.name}>"


# ── 日线行情 ──────────────────────────────────────────────

class DailyPrice(Base):
    __tablename__ = "daily_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), ForeignKey("stocks.symbol"), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Float, comment="开盘价")
    high = Column(Float, comment="最高价")
    low = Column(Float, comment="最低价")
    close = Column(Float, comment="收盘价")
    adj_close = Column(Float, comment="复权收盘价")
    volume = Column(Float, comment="成交量(股)")
    turnover = Column(Float, comment="成交额(元)")
    turnover_rate = Column(Float, comment="换手率(%)")
    market_cap = Column(Float, comment="当日总市值(元)")

    stock = relationship("Stock", back_populates="daily_prices")

    __table_args__ = (
        Index("ix_daily_prices_symbol_date", "symbol", "date", unique=True),
    )


# ── 历年分红（一级核心表） ────────────────────────────────

class Dividend(Base):
    __tablename__ = "dividends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), ForeignKey("stocks.symbol"), nullable=False)
    report_year = Column(Integer, comment="所属财年(如2025)")
    dividend_type = Column(String(20), comment="分红类型: annual/interim/quarterly/special/other")

    # 关键日期
    board_plan_date = Column(Date, comment="董事会预案公告日")
    shareholder_meeting_date = Column(Date, comment="股东大会通过日")
    execution_announcement_date = Column(Date, comment="正式实施公告日")
    record_date = Column(Date, comment="股权登记日")
    ex_date = Column(Date, comment="除权除息日")
    payment_date = Column(Date, comment="现金到账日")

    # 分红方案
    cash_div_per_share = Column(Float, comment="每股现金分红(元)")
    cash_div_per_10_shares = Column(Float, comment="每10股现金分红(元)")
    bonus_shares_ratio = Column(Float, comment="每10股送股比例")
    transfer_ratio = Column(Float, comment="每10股转增比例")

    # 金额
    total_cash_dividend = Column(Float, comment="现金分红总额(元)")
    net_profit = Column(Float, comment="归母净利润(元)")
    operating_cf = Column(Float, comment="经营现金流(元)")
    free_cf = Column(Float, comment="自由现金流(元)")

    # 自动计算
    payout_ratio = Column(Float, comment="派息率(分红/净利润)")
    fcf_payout_ratio = Column(Float, comment="FCF派息率(分红/自由现金流)")

    # 状态
    status = Column(String(20), comment="状态: proposed/approved/confirmed/executed")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    stock = relationship("Stock", back_populates="dividends")

    __table_args__ = (
        Index("ix_dividends_symbol_year", "symbol", "report_year"),
        Index("ix_dividends_ex_date", "ex_date"),
        Index(
            "ux_dividends_identity", "symbol", "report_year",
            "dividend_type", "ex_date", "cash_div_per_share", unique=True,
        ),
    )


# ── 财务报表 ──────────────────────────────────────────────

class FinancialStatement(Base):
    __tablename__ = "financial_statements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), ForeignKey("stocks.symbol"), nullable=False)
    report_date = Column(Date, nullable=False, comment="报告期(如2025-12-31)")
    report_type = Column(String(10), comment="报告类型: Q1/H1/Q3/annual")

    # 利润表
    revenue = Column(Float, comment="营业收入(元)")
    revenue_yoy = Column(Float, comment="营收同比(%)")
    net_profit = Column(Float, comment="归母净利润(元)")
    net_profit_yoy = Column(Float, comment="净利润同比(%)")
    eps = Column(Float, comment="每股收益(元)")
    gross_margin = Column(Float, comment="毛利率(%)")
    net_margin = Column(Float, comment="净利率(%)")
    operating_margin = Column(Float, comment="营业利润率(%)")

    # 资产负债表
    total_assets = Column(Float, comment="总资产(元)")
    total_liabilities = Column(Float, comment="总负债(元)")
    shareholders_equity = Column(Float, comment="股东权益(元)")
    debt_ratio = Column(Float, comment="资产负债率(%)")
    current_ratio = Column(Float, comment="流动比率")
    quick_ratio = Column(Float, comment="速动比率")

    # 现金流
    operating_cf = Column(Float, comment="经营活动现金流(元)")
    investing_cf = Column(Float, comment="投资活动现金流(元)")
    financing_cf = Column(Float, comment="筹资活动现金流(元)")
    free_cf = Column(Float, comment="自由现金流(元)")

    # 盈利能力
    roe = Column(Float, comment="净资产收益率ROE(%)")
    roa = Column(Float, comment="总资产收益率ROA(%)")

    # 现金流质量
    ocf_to_net_income = Column(Float, comment="经营现金流/净利润")

    created_at = Column(DateTime, default=datetime.utcnow)

    stock = relationship("Stock", back_populates="financial_statements")

    __table_args__ = (
        Index("ix_financials_symbol_date", "symbol", "report_date"),
        Index("ux_financials_symbol_date", "symbol", "report_date", unique=True),
    )


# ── 估值历史 ──────────────────────────────────────────────

class ValuationHistory(Base):
    __tablename__ = "valuation_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), ForeignKey("stocks.symbol"), nullable=False)
    date = Column(Date, nullable=False)

    # 估值指标
    pe_ttm = Column(Float, comment="PE(TTM)")
    pb = Column(Float, comment="PB")
    ps = Column(Float, comment="PS")
    ev_ebitda = Column(Float, comment="EV/EBITDA")

    # 股息率
    dividend_yield_ttm = Column(Float, comment="TTM股息率(%)")
    dividend_yield_annual = Column(Float, comment="年度股息率(%)")
    dividend_yield_forward = Column(Float, comment="Forward股息率(%)")

    # 历史百分位
    pe_percentile_3y = Column(Float, comment="PE 3年百分位")
    pe_percentile_5y = Column(Float, comment="PE 5年百分位")
    pe_percentile_10y = Column(Float, comment="PE 10年百分位")
    pb_percentile_3y = Column(Float, comment="PB 3年百分位")
    pb_percentile_5y = Column(Float, comment="PB 5年百分位")
    pb_percentile_10y = Column(Float, comment="PB 10年百分位")
    yield_percentile_3y = Column(Float, comment="股息率3年百分位")
    yield_percentile_5y = Column(Float, comment="股息率5年百分位")
    yield_percentile_10y = Column(Float, comment="股息率10年百分位")

    __table_args__ = (
        Index("ix_valuation_symbol_date", "symbol", "date"),
    )


# ── 因子评分 ──────────────────────────────────────────────

class FactorScore(Base):
    __tablename__ = "factor_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), ForeignKey("stocks.symbol"), nullable=False)
    date = Column(Date, nullable=False)

    # 七维评分
    yield_score = Column(Float, comment="股息率评分(0-100)")
    stability_score = Column(Float, comment="分红稳定性评分(0-100)")
    growth_score = Column(Float, comment="股息增长评分(0-100)")
    payout_score = Column(Float, comment="派息可持续性评分(0-100)")
    cashflow_score = Column(Float, comment="现金流评分(0-100)")
    quality_score = Column(Float, comment="财务质量评分(0-100)")
    valuation_score = Column(Float, comment="估值评分(0-100)")

    composite_score = Column(Float, comment="综合评分(0-100)")
    dividend_trap_risk = Column(String(10), comment="陷阱风险: LOW/MEDIUM/HIGH/EXTREME")

    # 排名百分位
    yield_rank_pct = Column(Float, comment="股息率排名百分位")
    stability_rank_pct = Column(Float, comment="稳定性排名百分位")

    __table_args__ = (
        Index("ix_factor_symbol_date", "symbol", "date"),
    )


# ── 数据同步状态 ──────────────────────────────────────────

class DataSyncState(Base):
    """Records successful/failed source refreshes, including empty results."""
    __tablename__ = "data_sync_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset = Column(String(30), nullable=False)
    symbol = Column(String(10), nullable=False)
    last_attempt_at = Column(DateTime)
    last_success_at = Column(DateTime)
    record_count = Column(Integer, default=0)
    last_error = Column(Text)

    __table_args__ = (
        Index("ux_sync_state_dataset_symbol", "dataset", "symbol", unique=True),
    )


# ── 用户自选 ──────────────────────────────────────────────

class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), ForeignKey("stocks.symbol"), nullable=False)
    added_date = Column(DateTime, default=datetime.utcnow)
    target_yield = Column(Float, comment="目标股息率(%)")
    target_price = Column(Float, comment="目标买入价(元)")
    notes = Column(Text, comment="用户备注")


# ── 持仓 ──────────────────────────────────────────────────

class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), ForeignKey("stocks.symbol"), nullable=False)
    buy_date = Column(Date, nullable=False, comment="买入日期")
    buy_price = Column(Float, nullable=False, comment="买入价格(元)")
    quantity = Column(Integer, nullable=False, comment="持有数量(股)")
    commission = Column(Float, default=0, comment="手续费(元)")
    cost_basis = Column(Float, comment="总成本(元)")
    yield_on_cost = Column(Float, comment="Yield on Cost(%)")
    notes = Column(Text, comment="备注")
    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("PortfolioTransaction", back_populates="position", lazy="dynamic")


class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, ForeignKey("portfolio_positions.id"), nullable=False)
    date = Column(Date, nullable=False)
    type = Column(String(20), nullable=False, comment="类型: buy/sell/dividend")
    price = Column(Float, comment="价格(元)")
    quantity = Column(Integer, comment="数量(股)")
    amount = Column(Float, comment="金额(元)")
    fees = Column(Float, default=0, comment="费用(元)")
    notes = Column(Text, comment="备注")

    position = relationship("PortfolioPosition", back_populates="transactions")


# ── 提醒规则 ──────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), ForeignKey("stocks.symbol"))
    rule_type = Column(String(50), nullable=False, comment="规则类型")
    threshold = Column(Float, nullable=False, comment="阈值")
    is_active = Column(Boolean, default=True)
    triggered_at = Column(DateTime, comment="最近触发时间")
    created_at = Column(DateTime, default=datetime.utcnow)


# ── 公告缓存 ──────────────────────────────────────────────

class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), ForeignKey("stocks.symbol"))
    title = Column(String(200), nullable=False)
    type = Column(String(50), comment="公告类型")
    publish_date = Column(Date)
    url = Column(String(500))
    summary = Column(Text, comment="摘要")
    keywords = Column(String(200), comment="关键词")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_announcements_symbol_date", "symbol", "publish_date"),
    )


# ── 回测结果 ──────────────────────────────────────────────

class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(100), nullable=False)
    params_json = Column(Text, comment="策略参数JSON")
    start_date = Column(Date)
    end_date = Column(Date)

    cagr = Column(Float, comment="年化收益率(%)")
    total_return = Column(Float, comment="总收益率(%)")
    annualized_vol = Column(Float, comment="年化波动率(%)")
    max_drawdown = Column(Float, comment="最大回撤(%)")
    sharpe = Column(Float)
    sortino = Column(Float)
    calmar = Column(Float)

    dividend_income = Column(Float, comment="累计分红收入(元)")
    dividend_cagr = Column(Float, comment="分红CAGR(%)")
    benchmark_cagr = Column(Float, comment="基准年化收益(%)")

    created_at = Column(DateTime, default=datetime.utcnow)
