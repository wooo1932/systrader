from __future__ import annotations
import os
import datetime
from fastapi import APIRouter, Query
from src.web.context import get_context
from src.core.log import get_log_buffer

router = APIRouter()


@router.get("/logs/live")
async def live_logs(after: int = Query(0)):
    buf = get_log_buffer()
    entries = buf.get_after(after)
    seq = entries[-1]["seq"] if entries else after
    return {"logs": entries, "seq": seq}


@router.get("/logs/dates")
async def log_dates():
    ctx = get_context()
    log_dir = ctx.get("log_dir", "logs")
    if not os.path.isdir(log_dir):
        return []
    files = sorted(os.listdir(log_dir), reverse=True)
    dates = []
    for f in files:
        if f.startswith("systrader.log.") or (f == "systrader.log"):
            if f == "systrader.log":
                dates.append(datetime.date.today().isoformat())
            else:
                date_part = f.replace("systrader.log.", "")
                if len(date_part) == 10:
                    dates.append(date_part)
    return dates


@router.get("/logs/{date}")
async def get_log_by_date(date: str, level: str = None, search: str = None):
    ctx = get_context()
    log_dir = ctx.get("log_dir", "logs")
    today = datetime.date.today().isoformat()

    if date == today:
        file_path = os.path.join(log_dir, "systrader.log")
    else:
        file_path = os.path.join(log_dir, f"systrader.log.{date}")

    if not os.path.isfile(file_path):
        return []

    lines = []
    with open(file_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if level and f"[{level.upper()}]" not in line:
                continue
            if search and search.lower() not in line.lower():
                continue
            lines.append(line.rstrip())
    return lines
