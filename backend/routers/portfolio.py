"""持仓管理API。"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional
from datetime import date
from database.engine import get_session
from database.models import PortfolioPosition, PortfolioTransaction

router = APIRouter()


class PositionCreate(BaseModel):
    symbol: str
    buy_date: str
    buy_price: float
    quantity: int
    commission: float = 0
    notes: Optional[str] = None


@router.get("/positions")
def list_positions():
    """获取持仓列表。"""
    session = get_session()
    try:
        positions = session.query(PortfolioPosition).all()
        return {
            "status": "ok",
            "data": [
                {
                    "id": p.id,
                    "symbol": p.symbol,
                    "buy_date": str(p.buy_date),
                    "buy_price": p.buy_price,
                    "quantity": p.quantity,
                    "cost_basis": p.cost_basis,
                    "yield_on_cost": p.yield_on_cost,
                    "notes": p.notes,
                }
                for p in positions
            ],
        }
    finally:
        session.close()


@router.post("/positions")
def add_position(pos: PositionCreate):
    """新增持仓。"""
    session = get_session()
    try:
        cost = pos.buy_price * pos.quantity + pos.commission
        position = PortfolioPosition(
            symbol=pos.symbol,
            buy_date=date.fromisoformat(pos.buy_date),
            buy_price=pos.buy_price,
            quantity=pos.quantity,
            commission=pos.commission,
            cost_basis=cost,
            notes=pos.notes,
        )
        session.add(position)
        session.commit()
        return {"status": "ok", "data": {"id": position.id}}
    finally:
        session.close()


@router.delete("/positions/{position_id}")
def delete_position(position_id: int):
    """删除持仓。"""
    session = get_session()
    try:
        pos = session.query(PortfolioPosition).filter(PortfolioPosition.id == position_id).first()
        if not pos:
            return {"status": "error", "error": "持仓不存在"}
        session.delete(pos)
        session.commit()
        return {"status": "ok"}
    finally:
        session.close()
