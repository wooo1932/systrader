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


@router.post("/telegram/auth-code")
async def telegram_auth_code(body: dict):
    ctx = get_context()
    telegram_news = ctx.get("telegram_news")
    if telegram_news:
        telegram_news.submit_auth_code(body.get("code", ""))
        return {"status": "ok"}
    return {"status": "error", "message": "telegram not configured"}
