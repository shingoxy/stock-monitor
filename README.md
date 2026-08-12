# A股高股息监控与投资研究平台

面向个人投资者的 A 股高股息股票研究、筛选、估值和风险识别工具。

## 已实现功能

- TTM / Annual / Forward / Proposed 多口径股息率
- 分红稳定性、连续分红年数和 3Y/5Y/10Y 增长率
- 10 条可追溯高股息陷阱规则
- 七维综合评分；缺失维度不再自动填充中性分，并返回评分覆盖率
- 高股息排行、条件筛选、收益率百分位机会雷达和分红日历
- 高股息股票卡片：代码、名称、价格、PE、今年 DPS、TTM DPS、股息率、增长和风险
- 持仓基础增删查；回测、提醒执行器和调度器仍属于后续功能

## 快速开始

```bash
pip install -r requirements.txt
python scripts/init_db.py
python scripts/sync_full.py
uvicorn backend.app:app --host 127.0.0.1 --port 3333
```

浏览器访问 `http://127.0.0.1:3333`，API 文档位于 `/docs`。

## 数据同步

核心数据库只接受东财、腾讯、新浪和 mootdx 的结构化结果。旧的 iFinD/Fuyao
自然语言导入入口保留为兼容命令，但会统一转到主链，避免多个写入器采用冲突口径。

```bash
# 股票主数据 + 分红 + 财务 + 当日行情/PE/PB/估值
python scripts/sync_full.py

# 同时补充历史日线（耗时较长）
python scripts/sync_full.py --with-history

# 只同步指定股票
python scripts/sync_full.py --symbols 000001 600519

# 单独刷新行情和估值
python scripts/data_fetcher.py --valuations
```

同步使用 upsert 和同步状态表，可安全重复执行。未来除息事件写为 `confirmed`，到达
除息日后才可进入 TTM 已实施分红。核心同步链不需要 MCP 凭据，任何可选凭据都只能
放在本地 `.env`，不得写入源码。

数据库历史污染修复默认只审计；执行修复前自动创建一致性 SQLite 备份：

```bash
python scripts/repair_database.py
python scripts/repair_database.py --apply
```

## 数据源

| 数据 | 主源 | 备注 |
|------|------|------|
| 实时行情、PE/PB | 腾讯财经 | 同步后从本地数据库读取 |
| K 线 | mootdx（通达信） | 用于历史价格和收益率历史 |
| 分红历史 | 东财 datacenter | 串行限流、增量 upsert |
| 财报三表 | 新浪财经 | 只接受真实报告期 |

## 项目结构

```text
config/          配置
data/            Provider 与缓存
database/        ORM 模型与引擎
factor/          因子和风险计算
backend/         FastAPI 与批量聚合服务
frontend/dist/   静态 Web UI
tests/           生产函数与公式测试
scripts/         同步、修复和初始化工具
```

## 免责声明

本项目仅提供数据分析工具，不构成任何投资建议。股市有风险，投资需谨慎。
