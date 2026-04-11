from __future__ import annotations
from fastapi import APIRouter, Query
from src.web.context import get_context

router = APIRouter()


@router.get("/stats/summary")
async def get_summary(date_from: str = None, date_to: str = None, source: str = None):
    ctx = get_context()
    db = ctx["db"]
    return db.daily_stats.get_summary(date_from=date_from, date_to=date_to, source=source)


@router.get("/stats/daily")
async def get_daily(days: int = Query(365), date_from: str = None, date_to: str = None,
                    source: str = None):
    ctx = get_context()
    db = ctx["db"]
    return db.daily_stats.get_range(days=days, date_from=date_from, date_to=date_to)
