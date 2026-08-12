"""初始化数据库 — 创建所有表。"""
import sys
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.engine import init_db, get_engine
from config.logging import setup_logging

logger = setup_logging()


def main():
    logger.info("初始化数据库...")
    init_db()
    engine = get_engine()
    table_names = list(engine.dialect.get_table_names(engine.connect()))
    logger.info(f"数据库初始化完成，共 {len(table_names)} 张表: {table_names}")


if __name__ == "__main__":
    main()
