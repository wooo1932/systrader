# SysTrader

## Overview

News scalping automated trading system using CYBOS Plus COM API.
Python 3.x (32-bit), FastAPI, SQLite, React+Vite frontend.

## Setup

```bash
# Requires 32-bit Python (CYBOS COM is 32-bit only)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# DB init
python -c "from src.database import Database; Database('data/systrader.db').ensure_schema()"

# Run
python main.py
```

## Commands

- `pytest` — Run tests
- `python main.py` — Start the system
- `cd web && npm run dev` — Start frontend dev server

## Architecture

- `src/com/` — CYBOS Plus COM wrappers (main thread STA only)
- `src/engine/` — Trading engine, worker state machine, BPI, screener
- `src/news/` — News sources (CYBOS events, Telegram)
- `src/web/` — FastAPI server, REST routes, WebSocket
- `src/core/` — EventBus, CommandQueue, logging
- `src/config.py` — Pydantic settings from appsettings.json
- `src/database.py` — SQLite repositories
- `src/models.py` — Pydantic models

## Conventions

- snake_case for JSON keys in API responses
- COM calls only on main thread via CommandQueue
- DB writes only from main thread (engine)
- DB reads allowed from any thread (SQLite WAL mode)
