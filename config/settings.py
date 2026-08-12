from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # 数据库
    database_url: str = Field(
        default=f"sqlite:///{BASE_DIR / 'stock_monitor.db'}",
        description="数据库连接URL",
    )

    # 日志
    log_level: str = Field(default="INFO", description="日志级别")
    log_dir: Path = Field(default=BASE_DIR / "logs", description="日志目录")

    # 东财限流
    em_min_interval: float = Field(
        default=1.0, description="东财请求最小间隔(秒)"
    )

    # 市场过滤
    include_bj_exchange: bool = Field(
        default=False, description="是否纳入北交所"
    )
    min_market_cap: float = Field(
        default=5e9, description="最低市值(元)"
    )
    min_dividend_yield: float = Field(
        default=0.01, description="最低股息率(小数，0.01=1%)"
    )
    default_yield_method: str = Field(
        default="ttm", description="默认股息率口径: ttm/annual/forward"
    )

    # 缓存
    cache_dir: Path = Field(
        default=BASE_DIR / ".cache", description="缓存目录"
    )

    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8"}


settings = Settings()
