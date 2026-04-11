from __future__ import annotations
from fastapi import APIRouter, Query
from src.web.context import get_context

router = APIRouter()


@router.get("/trades")
async def list_trades(status: str = None, date: str = None,
                      limit: int = Query(100), news_source: str = None):
    ctx = get_context()
    db = ctx["db"]
    return db.trades.list(status=status, date=date, limit=limit, news_source=news_source)


@router.get("/trades/{trade_id}")
async def get_trade(trade_id: int):
    ctx = get_context()
    db = ctx["db"]
    trade = db.trades.get(trade_id)
    if not trade:
        return {"error": "not found"}
    executions = db.executions.get_by_trade(trade_id)
    trade["executions"] = executions
    return trade


@router.get("/trades/{trade_id}/ticks")
async def get_ticks(trade_id: int):
    ctx = get_context()
    db = ctx["db"]
    return db.ticks.get_by_trade(trade_id)
