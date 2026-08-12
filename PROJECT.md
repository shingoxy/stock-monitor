# A股高股息监控与投资研究平台

## 项目概述

面向个人投资者的A股高股息股票研究、筛选、估值、风险识别、持仓跟踪、分红事件监控和投资机会提醒系统。

**核心目标**：不是简单展示"股息率排行榜"，而是建立一套能够长期运行的高股息股票研究系统。

---

## 快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python scripts/init_db.py

# 导入股票列表
python scripts/seed_stocks.py

# 采集分红+财务数据
python scripts/data_fetcher.py --all

# 启动服务（0.0.0.0:3333，内网可访问）
python -m uvicorn backend.app:app --host 0.0.0.0 --port 3333
```

---

## 当前数据状态

| 指标 | 数量 |
|------|------|
| 全量A股 | 4840只 |
| 有分红数据 | 283只 |
| 分红记录 | 4264条 |
| 财务数据 | 100只股票 |

---

## 技术架构

```
stock-monitor/
├── config/              配置系统（Pydantic BaseSettings）
├── data/                数据层（Provider抽象+缓存）
│   └── providers/       东财/腾讯/新浪/mootdx Provider
├── database/            数据库层（SQLAlchemy ORM）
├── factor/              因子计算层（7大因子模块）
├── strategy/            策略层（筛选器+预设策略）
├── backtest/            回测层
├── portfolio/           持仓管理层
├── alert/               提醒层
├── scheduler/           调度层
├── backend/             FastAPI后端
├── frontend/            前端Dashboard
├── tests/               测试
└── scripts/             工具脚本
```

---

## 数据源

| 数据 | 主源 | 风险 | 说明 |
|------|------|------|------|
| 实时行情 | 腾讯财经 | 极低 | 不封IP，PE/PB/市值/换手率 |
| K线 | mootdx | 极低 | TCP协议，通达信服务器 |
| 分红历史 | 东财datacenter | 中 | 需限流，1秒/请求 |
| 财报三表 | 新浪财经 | 低 | 利润表/资产负债表/现金流量表 |
| 公告 | 巨潮cninfo | 低 | 沪深北全量公告 |

**重要**：系统有macOS代理兼容层，自动绕过系统代理直连数据源。

---

## 因子计算体系

### 1. 股息率计算（4种口径）

| 口径 | 公式 | 用途 |
|------|------|------|
| TTM Yield | 过去12月实际DPS / 当前价 | 默认排行/筛选 |
| Annual Yield | 最近完整财年DPS / 当前价 | 年度对比 |
| Forward Yield | 已公告未派DPS / 当前价 | 预期收益 |
| Proposed Yield | 董事会预案DPS / 当前价 | 预案参考 |

### 2. 分红稳定性评分（0-100分）

评分维度：
- 连续分红年数（最高30分）
- 分红波动率CV（最高30分）
- 分红下降次数（最高20分）
- 活跃年份（最高20分）

评级：S(≥85) / A(≥70) / B(≥55) / C(≥40) / D(<40)

### 3. 股息增长率

计算 3Y / 5Y / 10Y 的 Dividend CAGR。

### 4. 派息率分析

- Payout Ratio = 现金分红 / 归母净利润
- FCF Payout = 现金分红 / 自由现金流
- FCF Coverage = FCF / 现金分红（>1表示可覆盖）

### 5. 高股息陷阱检测（10条规则）

| 规则 | 说明 |
|------|------|
| R1 | 公司亏损但仍分红 |
| R2 | 净利润连续3期下降 |
| R3 | FCF无法覆盖分红 |
| R4 | 派息率>100% |
| R5 | 高负债(>70%)仍大额分红 |
| R6 | 存在特别分红 |
| R9 | 净利润同比下降>30% |

风险等级：LOW / MEDIUM / HIGH / EXTREME

### 6. 综合评分（7维，0-100分）

| 维度 | 权重 | 说明 |
|------|------|------|
| 股息率 | 25% | TTM Yield评分 |
| 分红稳定性 | 20% | 连续年数/波动/下降次数 |
| 股息增长 | 10% | 5Y CAGR |
| 派息可持续性 | 15% | Payout + FCF Coverage |
| 现金流 | 10% | OCF/NI比率 |
| 财务质量 | 10% | ROE + 负债率 |
| 估值 | 10% | 股息率历史百分位 |

---

## API端点

### 市场总览

```
GET /api/market/overview
```

返回：全A股票数、有分红数据数、股息率分布(≥3%/4%/5%/6%/7%/8%)、行业平均股息率。

### 高股息排行

```
GET /api/dividends/ranking?min_yield=3&min_years=3&page_size=50
```

参数：
- `min_yield`: 最低股息率(%)，默认3
- `min_years`: 最低连续分红年数，默认3
- `page`: 页码
- `page_size`: 每页条数

### 机会雷达

```
GET /api/dividends/opportunities?percentile_threshold=80
```

返回股息率进入历史高位的股票。

### 分红日历

```
GET /api/dividends/calendar?days=30
```

返回未来N天的除权除息日。

### 高级筛选

```
POST /api/screener/run?min_yield=5&min_years=5&min_roe=10&min_mcap=10000000000
```

### 股票详情

```
GET /api/stocks/{symbol}/detail
```

返回完整分析：基本信息、股息率、稳定性、增长、财务、陷阱检测、综合评分、历史DPS、目标股价矩阵。

### 预设策略

```
GET /api/screener/presets
```

返回内置策略：高股息蓝筹、稳定高股息、高股息成长、现金奶牛。

---

## 前端Dashboard

访问：`http://<IP>:3333`

### 功能页面

1. **市场总览** - 股息率分布卡片 + 行业平均股息率柱状图
2. **高股息排行** - 可调阈值的排行榜，点击查看详情
3. **筛选器** - 组合条件筛选
4. **机会雷达** - 股息率进入历史高位的股票
5. **分红日历** - 未来除权除息日
6. **股票详情弹窗** - 完整分析面板

### 设计风格

- 暗色主题（专业金融终端风格）
- 红涨绿跌（A股习惯）
- 评分/风险独立颜色体系（蓝/绿/橙/红）
- 响应式布局

---

## 数据库Schema

### stocks（股票基本信息）

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | String(10) PK | 股票代码 |
| name | String(50) | 公司名称 |
| exchange | String(5) | 交易所SH/SZ/BJ |
| industry | String(50) | 行业分类 |
| listing_date | Date | 上市日期 |
| status | String(10) | 状态active/st/suspended/delisted |
| total_market_cap | Float | 总市值(元) |
| float_market_cap | Float | 流通市值(元) |

### dividends（分红记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | String(10) FK | 股票代码 |
| report_year | Integer | 所属财年 |
| dividend_type | String(20) | annual/interim/quarterly/special |
| board_plan_date | Date | 董事会预案公告日 |
| ex_date | Date | 除权除息日 |
| payment_date | Date | 现金到账日 |
| cash_div_per_share | Float | 每股现金分红(元) |
| status | String(20) | proposed/approved/confirmed/executed |

### financial_statements（财务报表）

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | String(10) FK | 股票代码 |
| report_date | Date | 报告期 |
| report_type | String(10) | Q1/H1/Q3/annual |
| revenue | Float | 营业收入 |
| net_profit | Float | 归母净利润 |
| roe | Float | ROE(%) |
| debt_ratio | Float | 资产负债率(%) |
| operating_cf | Float | 经营现金流 |
| free_cf | Float | 自由现金流 |

---

## 股息率估值体系

### 历史百分位

计算当前股息率在过去N年中的位置：

- < P20：低股息率 / 相对高估区
- P20-P50：正常偏低
- P50-P80：正常偏高
- P80-P90：高股息关注区
- > P90：历史极高股息区

### 目标股价矩阵

根据目标股息率反推股价：

```
DPS = 2.50元

目标Yield → 对应股价
4% → 62.50
5% → 50.00
6% → 41.67
7% → 35.71
8% → 31.25
```

---

## 测试

```bash
# 运行测试
python -m pytest tests/ -v

# 测试结果
tests/test_dividend_yield.py::test_ttm_yield_basic PASSED
tests/test_dividend_yield.py::test_yield_with_zero_price PASSED
tests/test_dividend_yield.py::test_yield_with_zero_dps PASSED
tests/test_dividend_yield.py::test_yield_with_negative_profit PASSED
tests/test_dividend_yield.py::test_target_price_calculation PASSED
tests/test_dividend_yield.py::test_payout_ratio PASSED
tests/test_dividend_yield.py::test_payout_ratio_over_100 PASSED
tests/test_dividend_yield.py::test_fcf_payout PASSED
tests/test_dividend_yield.py::test_dividend_cagr PASSED
tests/test_dividend_yield.py::test_yield_percentile PASSED
```

---

## 配置

### 环境变量（.env）

```bash
DATABASE_URL=sqlite:///./stock_monitor.db
LOG_LEVEL=INFO
EM_MIN_INTERVAL=1.0
INCLUDE_BJ_EXCHANGE=false
MIN_MARKET_CAP=5000000000
DEFAULT_YIELD_METHOD=ttm
```

### 预设策略

内置4个策略：
1. **高股息蓝筹** - Yield≥5%, 连续分红≥5年, ROE≥10%, 市值≥500亿
2. **稳定高股息** - Yield≥4%, 连续分红≥10年
3. **高股息成长** - Yield≥3%, 连续分红≥3年
4. **现金奶牛** - Yield≥4%, ROE≥12%

---

## 已知限制

1. **数据覆盖**：当前仅拉取了300只高市值股票的分红数据，全量数据需分批拉取
2. **历史K线**：mootdx连接不稳定，暂未拉取历史K线数据
3. **实时行情**：依赖腾讯API，需网络可达
4. **代理兼容**：已自动处理macOS系统代理，其他系统需测试

---

## 后续优化方向

### PHASE 3（待实现）
- 历史K线数据入库（mootdx/腾讯）
- 估值历史百分位计算
- 股息率历史序列图表

### PHASE 4（待实现）
- 持仓管理CRUD
- Yield on Cost计算
- 分红现金流预测
- DRIP模拟

### PHASE 5（待实现）
- 回测引擎（Point-in-Time）
- 组合构建
- 风险分析

### PHASE 6（待实现）
- 提醒系统（价格/股息率/百分位触发）
- 公告监控
- 定时任务调度

---

## 技术栈

| 层 | 技术 |
|------|------|
| 后端 | Python 3.9+ / FastAPI / SQLAlchemy |
| 数据分析 | pandas / numpy |
| 数据源 | 腾讯财经 / 东财datacenter / 新浪财经 / mootdx |
| 前端 | 原生HTML/CSS/JS（暗色主题） |
| 数据库 | SQLite（可切PostgreSQL） |
| 日志 | loguru（rotation + 分级） |

---

## 免责声明

本项目仅提供数据分析工具，不构成任何投资建议。股市有风险，投资需谨慎。

---

## 项目信息

- **版本**：0.1.0
- **创建时间**：2026-08-10
- **Python版本**：3.9.16
- **许可证**：MIT
