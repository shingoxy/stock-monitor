import sys
from pathlib import Path
from loguru import logger
from config.settings import settings


def setup_logging():
    """配置结构化日志，支持文件rotation。"""
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()

    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
    )

    logger.add(
        settings.log_dir / "app_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
               "{name}:{function}:{line} | {message}",
    )

    logger.add(
        settings.log_dir / "error_{time:YYYY-MM-DD}.log",
        level="ERROR",
        rotation="1 day",
        retention="60 days",
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
               "{name}:{function}:{line} | {message}",
    )

    return logger
