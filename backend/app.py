"""FastAPI 后端应用。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.routers import stocks, dividends, screener, market, portfolio
from config.logging import setup_logging

setup_logging()

app = FastAPI(
    title="A股高股息监控平台",
    description="面向个人投资者的A股高股息股票研究、筛选、估值系统",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router, prefix="/api/stocks", tags=["stocks"])
app.include_router(dividends.router, prefix="/api/dividends", tags=["dividends"])
app.include_router(screener.router, prefix="/api/screener", tags=["screener"])
app.include_router(market.router, prefix="/api/market", tags=["market"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])

# 前端静态文件
frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = frontend_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dir / "index.html"))
else:
    @app.get("/")
    async def root():
        return {
            "message": "A股高股息监控平台 API",
            "docs": "/docs",
            "endpoints": [
                "/api/stocks/list",
                "/api/stocks/{symbol}",
                "/api/stocks/{symbol}/detail",
                "/api/dividends/ranking",
                "/api/dividends/opportunities",
                "/api/screener/run",
                "/api/market/overview",
            ],
        }
