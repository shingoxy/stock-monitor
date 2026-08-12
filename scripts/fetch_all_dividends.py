"""Synchronize dividends for all active A-share stocks."""
from database.engine import init_db
from scripts.data_fetcher import fetch_dividends


if __name__ == "__main__":
    init_db()
    fetch_dividends()
