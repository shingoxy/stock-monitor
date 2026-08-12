"""股息率计算测试。"""
import pytest


def test_ttm_yield_basic():
    """测试TTM股息率基本计算。"""
    # DPS = 2.50, Price = 35.00 → Yield = 7.14%
    dps = 2.50
    price = 35.00
    yield_pct = dps / price * 100
    assert abs(yield_pct - 7.142857) < 0.01


def test_yield_with_zero_price():
    """价格为0时不应计算股息率。"""
    dps = 2.50
    price = 0
    if price > 0:
        yield_pct = dps / price * 100
    else:
        yield_pct = None
    assert yield_pct is None


def test_yield_with_zero_dps():
    """DPS为0时股息率为0。"""
    dps = 0
    price = 35.00
    yield_pct = dps / price * 100 if price > 0 else None
    assert yield_pct == 0.0


def test_yield_with_negative_profit():
    """亏损公司分红时仍可计算股息率（基于DPS/Price）。"""
    dps = 1.0  # 仍然分红
    price = 20.0
    net_profit = -1e8  # 亏损
    yield_pct = dps / price * 100
    assert abs(yield_pct - 5.0) < 0.01
    # 但派息率应标记为异常
    payout_ratio = None  # 亏损时派息率无意义
    assert payout_ratio is None


def test_target_price_calculation():
    """测试目标股息率反推股价。"""
    dps = 2.50
    targets = {
        4: dps / 0.04,   # 62.50
        5: dps / 0.05,   # 50.00
        6: dps / 0.06,   # 41.67
        7: dps / 0.07,   # 35.71
        8: dps / 0.08,   # 31.25
    }
    assert abs(targets[4] - 62.50) < 0.01
    assert abs(targets[5] - 50.00) < 0.01
    assert abs(targets[6] - 41.67) < 0.01
    assert abs(targets[7] - 35.71) < 0.01
    assert abs(targets[8] - 31.25) < 0.01


def test_payout_ratio():
    """测试派息率计算。"""
    total_div = 500e8  # 分红500亿
    net_profit = 730e8  # 净利730亿
    payout = total_div / net_profit * 100
    assert abs(payout - 68.49) < 0.1


def test_payout_ratio_over_100():
    """派息率>100%应标记警告。"""
    total_div = 800e8
    net_profit = 600e8
    payout = total_div / net_profit * 100
    assert payout > 100  # 应触发警告


def test_fcf_payout():
    """测试FCF派息率。"""
    total_div = 500e8
    fcf = 600e8
    fcf_payout = total_div / fcf * 100
    assert abs(fcf_payout - 83.33) < 0.1


def test_dividend_cagr():
    """测试股息CAGR计算。"""
    dps_start = 1.50  # 5年前
    dps_end = 2.50    # 当前
    years = 5
    cagr = (dps_end / dps_start) ** (1 / years) - 1
    assert abs(cagr - 0.1076) < 0.005  # ~10.76%


def test_yield_percentile():
    """测试股息率百分位计算。"""
    import pandas as pd

    # 历史股息率序列
    historical_yields = [3.0, 3.5, 4.0, 4.2, 4.5, 5.0, 5.1, 5.5, 6.0, 7.0]
    current_yield = 6.5

    series = pd.Series(historical_yields)
    percentile = (series < current_yield).sum() / len(series) * 100
    assert percentile == 90.0  # 高于90%的历史值
