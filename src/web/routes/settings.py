from __future__ import annotations
import json
from fastapi import APIRouter
from src.web.context import get_context

router = APIRouter()


@router.get("/settings/params")
async def get_params():
    ctx = get_context()
    return ctx["db"].params.get_all()


@router.put("/settings/params/{key}")
async def update_param(key: str, body: dict):
    ctx = get_context()
    value = str(body.get("value", ""))
    ctx["db"].params.upsert(key, value, "user")
    engine = ctx.get("engine")
    if engine and engine.running:
        engine._load_params()
    return {"status": "ok"}


@router.get("/settings/params/history")
async def get_param_history():
    ctx = get_context()
    return ctx["db"].params.get_history()


@router.get("/settings/config")
async def get_config():
    ctx = get_context()
    settings_path = ctx.get("settings_path", "appsettings.json")
    with open(settings_path, encoding="utf-8") as f:
        return json.load(f)


@router.put("/settings/config")
async def update_config(body: dict):
    ctx = get_context()
    settings_path = ctx.get("settings_path", "appsettings.json")
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2, ensure_ascii=False)
    return {"status": "ok"}


@router.get("/settings/channels")
async def list_channels():
    ctx = get_context()
    return ctx["db"].channels.list()


@router.post("/settings/channels")
async def create_channel(body: dict):
    ctx = get_context()
    channel_id = ctx["db"].channels.create(
        body.get("channel_url", ""), body.get("channel_name", "")
    )
    return {"id": channel_id, "status": "ok"}


@router.delete("/settings/channels/{channel_id}")
async def delete_channel(channel_id: int):
    ctx = get_context()
    ctx["db"].channels.delete(channel_id)
    return {"status": "ok"}


@router.put("/settings/channels/{channel_id}/toggle")
async def toggle_channel(channel_id: int):
    ctx = get_context()
    ctx["db"].channels.toggle(channel_id)
    return {"status": "ok"}
