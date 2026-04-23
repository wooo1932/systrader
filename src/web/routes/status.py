from __future__ import annotations
import os
from fastapi import APIRouter
from src.web.context import get_context

router = APIRouter()


@router.get("/status")
async def get_status():
    ctx = get_context()
    engine = ctx.get("engine")
    telegram_news = ctx.get("telegram_news")
    return {
        "cybos_connected": ctx.get("cybos_connected", False),
        "server_type": ctx.get("server_type", ""),
        "engine_running": engine.running if engine else False,
        "active_workers": engine.active_worker_count if engine else 0,
        "account_number": ctx.get("account_number", ""),
        "error": None,
        "telegram_code_pending": getattr(telegram_news, "_auth_code_future", None) is not None
            if telegram_news else False,
    }


@router.post("/engine/start")
async def engine_start():
    ctx = get_context()
    cmd_queue = ctx.get("command_queue")
    future = cmd_queue.put("engine_start", {})
    return {"status": "ok"}


@router.post("/engine/stop")
async def engine_stop():
    ctx = get_context()
    cmd_queue = ctx.get("command_queue")
    future = cmd_queue.put("engine_stop", {})
    return {"status": "ok"}


@router.post("/daily-summary")
async def send_daily_summary(body: dict = None):
    ctx = get_context()
    cmd_queue = ctx.get("command_queue")
    if not cmd_queue:
        return {"status": "error", "message": "command queue not available"}
    params = body or {}
    cmd_queue.put("send_daily_summary", params)
    return {"status": "ok"}


@router.post("/engine/launch-cybos")
async def launch_cybos():
    ctx = get_context()
    settings = ctx.get("settings")
    if settings:
        try:
            import ctypes
            exe_path = settings.cybos.exe_path
            work_dir = os.path.dirname(exe_path)
            # ShellExecute "open" with /prj:cp arg (CYBOS Plus mode), cwd=exe dir
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "open", exe_path, "/prj:cp", work_dir, 1
            )
            if rc <= 32:
                return {"status": "error", "message": f"ShellExecute failed (code={rc})"}
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "settings not available"}


@router.get("/reconciliation")
async def get_reconciliation():
    ctx = get_context()
    engine = ctx.get("engine")

    # Read from main-thread-refreshed cache (avoids COM marshalling in web thread)
    broker_holdings = ctx.get("holdings_cache")
    if broker_holdings is None:
        return {"error": "holdings cache not ready (CYBOS not connected or first poll pending)"}
    broker_map = {h["code"]: h for h in broker_holdings}

    system_holdings = {}
    if engine:
        for code, worker in engine.workers.items():
            if worker.state.value == "holding":
                system_holdings[code] = {
                    "code": code, "name": worker.stock_name,
                    "quantity": worker.buy_qty, "price": worker.buy_price,
                }

    all_codes = set(broker_map.keys()) | set(system_holdings.keys())
    discrepancies = []
    for code in all_codes:
        broker = broker_map.get(code)
        system = system_holdings.get(code)
        if broker and not system:
            discrepancies.append({
                "code": code, "name": broker["name"], "type": "broker_only",
                "broker_qty": broker["quantity"], "system_qty": 0,
            })
        elif system and not broker:
            discrepancies.append({
                "code": code, "name": system["name"], "type": "system_only",
                "broker_qty": 0, "system_qty": system["quantity"],
            })
        elif broker["quantity"] != system["quantity"]:
            discrepancies.append({
                "code": code, "name": broker["name"], "type": "qty_mismatch",
                "broker_qty": broker["quantity"], "system_qty": system["quantity"],
            })

    return {
        "broker_holdings": broker_holdings,
        "system_holdings": list(system_holdings.values()),
        "discrepancies": discrepancies,
        "matched": len(discrepancies) == 0,
    }


@router.post("/emergency/sell-all")
async def emergency_sell_all():
    """Liquidate all HOLDING positions at market immediately. Also stops engine
    so no new buys enter. Does NOT cancel BUYING workers — those clear via
    BUYING timeout."""
    ctx = get_context()
    cmd_queue = ctx.get("command_queue")
    if not cmd_queue:
        return {"status": "error", "message": "command queue not available"}
    cmd_queue.put("emergency_sell_all", {})
    return {"status": "ok"}


@router.post("/telegram/auth-code")
async def telegram_auth_code(body: dict):
    ctx = get_context()
    telegram_news = ctx.get("telegram_news")
    if telegram_news:
        telegram_news.submit_auth_code(body.get("code", ""))
        return {"status": "ok"}
    return {"status": "error", "message": "telegram not configured"}
