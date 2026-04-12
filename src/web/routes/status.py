from __future__ import annotations
import subprocess
from fastapi import APIRouter
from src.web.context import get_context

router = APIRouter()


@router.get("/status")
async def get_status():
    ctx = get_context()
    engine = ctx.get("engine")
    connection = ctx.get("connection")
    account = ctx.get("account")
    telegram_news = ctx.get("telegram_news")
    return {
        "cybos_connected": connection.is_connected if connection else False,
        "server_type": connection.get_server_type() if connection else "",
        "engine_running": engine.running if engine else False,
        "active_workers": engine.active_worker_count if engine else 0,
        "account_number": account.account_number if account else "",
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


@router.post("/engine/launch-cybos")
async def launch_cybos():
    ctx = get_context()
    settings = ctx.get("settings")
    if settings:
        try:
            subprocess.Popen(settings.cybos.exe_path)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "settings not available"}


@router.get("/reconciliation")
async def get_reconciliation():
    ctx = get_context()
    engine = ctx.get("engine")
    balance = ctx.get("balance")

    if not balance:
        return {"error": "balance not available (CYBOS not connected)"}

    broker_holdings = balance.get_holdings()
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


@router.post("/telegram/auth-code")
async def telegram_auth_code(body: dict):
    ctx = get_context()
    telegram_news = ctx.get("telegram_news")
    if telegram_news:
        telegram_news.submit_auth_code(body.get("code", ""))
        return {"status": "ok"}
    return {"status": "error", "message": "telegram not configured"}
