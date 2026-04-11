# SysTrader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python-based news scalping automated trading system using CYBOS Plus COM API, with FastAPI backend and reused React+Vite frontend.

**Architecture:** Single-process, multi-thread. Main thread runs COM STA with message pump + trading engine. FastAPI runs in daemon thread. Telethon and Telegram bot each run in their own daemon threads. Communication via thread-safe EventBus (events flow out from COM) and CommandQueue (commands flow in to COM).

**Tech Stack:** Python 3.x (32-bit), FastAPI, uvicorn, SQLite, win32com, pythoncom, Telethon, python-telegram-bot, Pydantic

---

## File Map

```
systrader/
├── CLAUDE.md                          # Project conventions
├── README.md                          # Setup instructions
├── .gitignore                         # Python gitignore
├── requirements.txt                   # Python dependencies
├── appsettings.json                   # App config (CYBOS, Telegram, Web, DB)
├── main.py                            # Entry point: COM STA loop + thread spawning
├── db/
│   └── schema.sql                     # SQLite DDL (7 tables)
├── data/                              # Runtime: systrader.db
├── logs/                              # Runtime: daily log files
├── poc/
│   └── test_news_event.py             # COM news event PoC
├── web/                               # React+Vite frontend (copied from autotrader)
├── tests/
│   ├── __init__.py
│   ├── test_tick_unit.py
│   ├── test_bpi.py
│   ├── test_screener.py
│   ├── test_worker.py
│   ├── test_event_bus.py
│   ├── test_command_queue.py
│   ├── test_config.py
│   ├── test_database.py
│   └── test_api.py
└── src/
    ├── __init__.py
    ├── config.py                      # Pydantic settings from appsettings.json
    ├── models.py                      # Pydantic models for Trade, Tick, etc.
    ├── database.py                    # SQLite connection + repositories
    ├── com/
    │   ├── __init__.py
    │   ├── connection.py              # CpCybos wrapper
    │   ├── code.py                    # CpStockCode + CpCodeMgr wrapper
    │   ├── stock.py                   # StockMst + StockCur + MarketEye
    │   ├── order.py                   # CpTd0311 + CpTd0314
    │   └── account.py                 # CpTdUtil wrapper
    ├── engine/
    │   ├── __init__.py
    │   ├── tick_unit.py               # Price tick unit table
    │   ├── bpi.py                     # BPI calculator
    │   ├── screener.py                # Stock filter
    │   ├── worker.py                  # StockWorker state machine
    │   └── trading_engine.py          # Engine orchestrator
    ├── news/
    │   ├── __init__.py
    │   ├── cybos_news.py              # CpSvr8092S event handler
    │   └── telegram_news.py           # Telethon channel listener
    ├── telegram/
    │   ├── __init__.py
    │   └── bot.py                     # Alert bot
    ├── web/
    │   ├── __init__.py
    │   ├── server.py                  # FastAPI app + uvicorn thread
    │   ├── websocket.py               # WS manager + EventBridge
    │   └── routes/
    │       ├── __init__.py
    │       ├── status.py              # /api/status, /api/engine/*
    │       ├── trades.py              # /api/trades*
    │       ├── stats.py               # /api/stats/*
    │       ├── settings.py            # /api/settings/*
    │       ├── news.py                # /api/news-feed, /api/test/news
    │       └── logs.py                # /api/logs/*
    └── core/
        ├── __init__.py
        ├── event_bus.py               # Thread-safe pub/sub
        ├── command_queue.py           # Main-thread command dispatch
        └── log.py                     # Logging + LogBuffer
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `systrader/.gitignore`
- Create: `systrader/CLAUDE.md`
- Create: `systrader/README.md`
- Create: `systrader/requirements.txt`
- Create: `systrader/appsettings.json`
- Create: `systrader/db/schema.sql`
- Create: `systrader/src/__init__.py`
- Create: `systrader/tests/__init__.py`

- [ ] **Step 1: Create .gitignore**

```
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.eggs/
*.egg
.env
*.db
data/
logs/
.venv/
venv/
node_modules/
web/dist/
*.session
*.session-journal
appsettings.json
```

- [ ] **Step 2: Create CLAUDE.md**

```markdown
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
```

- [ ] **Step 3: Create requirements.txt**

```
fastapi==0.115.12
uvicorn==0.34.2
pydantic==2.11.3
pywin32==310
telethon==1.39.0
python-telegram-bot==22.2
aiosqlite==0.21.0
```

- [ ] **Step 4: Create appsettings.example.json**

```json
{
  "Cybos": {
    "ExePath": "C:\\DAISHIN\\STARTER\\ncStarter.exe"
  },
  "TelegramListener": {
    "ApiId": 0,
    "ApiHash": "",
    "Phone": "",
    "SessionName": "systrader_listener"
  },
  "TelegramBot": {
    "Token": "",
    "ChatId": 0
  },
  "Web": {
    "Host": "0.0.0.0",
    "Port": 8000
  },
  "Db": {
    "Path": "data/systrader.db"
  },
  "Logging": {
    "Dir": "logs",
    "LogLevel": "INFO"
  }
}
```

- [ ] **Step 5: Create db/schema.sql**

```sql
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    news_source TEXT NOT NULL,
    news_channel TEXT,
    news_text TEXT,
    buy_price REAL,
    buy_qty INTEGER,
    buy_time TEXT,
    buy_order_price REAL,
    sell_price REAL,
    sell_qty INTEGER,
    sell_time TEXT,
    sell_reason TEXT,
    pnl_pct REAL,
    pnl_amount REAL,
    highest_price REAL,
    hold_seconds REAL,
    status TEXT NOT NULL DEFAULT 'screening',
    parameter_snapshot TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS trade_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL REFERENCES trades(id),
    side TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    executed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL REFERENCES trades(id),
    stock_code TEXT NOT NULL,
    price REAL NOT NULL,
    volume INTEGER NOT NULL,
    bid_or_ask TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parameters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_by TEXT DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS parameter_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_url TEXT UNIQUE NOT NULL,
    channel_name TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    total_trades INTEGER DEFAULT 0,
    win_count INTEGER DEFAULT 0,
    loss_count INTEGER DEFAULT 0,
    win_rate REAL DEFAULT 0.0,
    total_pnl REAL DEFAULT 0.0,
    avg_pnl_pct REAL DEFAULT 0.0,
    best_trade_pnl REAL DEFAULT 0.0,
    worst_trade_pnl REAL DEFAULT 0.0,
    avg_hold_seconds REAL DEFAULT 0.0,
    news_source_stats TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at);
CREATE INDEX IF NOT EXISTS idx_ticks_trade_id ON ticks(trade_id);
CREATE INDEX IF NOT EXISTS idx_trade_executions_trade_id ON trade_executions(trade_id);
```

- [ ] **Step 6: Create empty __init__.py files**

Create empty files at:
- `src/__init__.py`
- `src/com/__init__.py`
- `src/engine/__init__.py`
- `src/news/__init__.py`
- `src/telegram/__init__.py`
- `src/web/__init__.py`
- `src/web/routes/__init__.py`
- `src/core/__init__.py`
- `tests/__init__.py`

- [ ] **Step 7: Create data/ and logs/ directories**

```bash
mkdir -p data logs poc
```

- [ ] **Step 8: Commit**

```bash
git add .gitignore CLAUDE.md README.md requirements.txt appsettings.example.json db/schema.sql src/ tests/ data/.gitkeep logs/.gitkeep poc/
git commit -m "chore: scaffold systrader project structure"
```

---

### Task 2: PoC — COM News Event Verification

**Files:**
- Create: `poc/test_news_event.py`

- [ ] **Step 1: Write the PoC script**

```python
"""
PoC: Verify CpSvr8092S news events fire in Python.
Run with 32-bit Python while CYBOS Plus is connected.

Usage: python poc/test_news_event.py
"""
import sys
import time
import pythoncom
import win32com.client
import win32event


class NewsHandler:
    received_count = 0

    def OnReceived(self):
        NewsHandler.received_count += 1
        code = self._obj.GetHeaderValue(1)
        title = self._obj.GetHeaderValue(5)
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] #{NewsHandler.received_count} code={code} title={title}")


def check_connection():
    cybos = win32com.client.Dispatch("CpUtil.CpCybos")
    if cybos.IsConnect == 0:
        print("ERROR: CYBOS Plus is not connected.")
        print("Launch CYBOS Plus and log in first.")
        sys.exit(1)
    server_type = cybos.GetStockMarketKind("A005930")
    print(f"CYBOS connected. Server type check: {server_type}")


def main():
    pythoncom.CoInitialize()
    check_connection()

    print("Subscribing to CpSvr8092S news events...")
    try:
        news = win32com.client.DispatchWithEvents("Dscbo1.CpSvr8092S", NewsHandler)
        news.Subscribe()
        print("Subscribed. Waiting for news events (Ctrl+C to stop)...")
    except Exception as e:
        print(f"DispatchWithEvents failed: {e}")
        print("Trying WithEvents pattern instead...")
        news_obj = win32com.client.Dispatch("Dscbo1.CpSvr8092S")
        handler = win32com.client.WithEvents(news_obj, NewsHandler)
        news_obj.Subscribe()
        print("WithEvents subscribed. Waiting for news events (Ctrl+C to stop)...")

    stop_event = win32event.CreateEvent(None, 0, 0, None)
    try:
        while True:
            rc = win32event.MsgWaitForMultipleObjects(
                [stop_event], 0, 1000, win32event.QS_ALLEVENTS
            )
            if rc == win32event.WAIT_OBJECT_0 + 1:
                pythoncom.PumpWaitingMessages()
            # Print heartbeat every 30 seconds
            if NewsHandler.received_count == 0 and int(time.time()) % 30 == 0:
                print(f"  ... still waiting (no events yet)")
    except KeyboardInterrupt:
        print(f"\nStopped. Total events received: {NewsHandler.received_count}")
        if NewsHandler.received_count == 0:
            print("No events received. Possible causes:")
            print("  1. No news published during test period")
            print("  2. CpSvr8092S events may not work in Python")
            print("  3. Try running during market hours")
        news.Unsubscribe()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add poc/test_news_event.py
git commit -m "feat: add COM news event PoC script"
```

- [ ] **Step 3: Run the PoC (manual, requires CYBOS Plus)**

```bash
# Run with 32-bit Python while CYBOS Plus is connected
python poc/test_news_event.py
```

Wait for news events during market hours. If events fire, the PoC is validated. If not, try the fallback patterns noted in the script.

---

### Task 3: Config & Models

**Files:**
- Create: `src/config.py`
- Create: `src/models.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write config test**

```python
# tests/test_config.py
import json
import os
import tempfile
import pytest
from src.config import load_settings, AppSettings


def _write_config(path, overrides=None):
    base = {
        "Cybos": {"ExePath": "C:\\DAISHIN\\STARTER\\ncStarter.exe"},
        "TelegramListener": {
            "ApiId": 123, "ApiHash": "abc", "Phone": "+8210", "SessionName": "test"
        },
        "TelegramBot": {"Token": "tok", "ChatId": 999},
        "Web": {"Host": "0.0.0.0", "Port": 8000},
        "Db": {"Path": "data/test.db"},
        "Logging": {"Dir": "logs", "LogLevel": "INFO"},
    }
    if overrides:
        base.update(overrides)
    with open(path, "w") as f:
        json.dump(base, f)


def test_load_settings_parses_all_sections(tmp_path):
    cfg_path = tmp_path / "appsettings.json"
    _write_config(str(cfg_path))
    settings = load_settings(str(cfg_path))
    assert isinstance(settings, AppSettings)
    assert settings.cybos.exe_path == "C:\\DAISHIN\\STARTER\\ncStarter.exe"
    assert settings.telegram_listener.api_id == 123
    assert settings.telegram_bot.chat_id == 999
    assert settings.web.port == 8000
    assert settings.db.path == "data/test.db"
    assert settings.logging.log_level == "INFO"


def test_load_settings_defaults(tmp_path):
    cfg_path = tmp_path / "appsettings.json"
    minimal = {
        "Cybos": {"ExePath": "c:\\test.exe"},
        "TelegramListener": {
            "ApiId": 1, "ApiHash": "x", "Phone": "+1", "SessionName": "s"
        },
        "TelegramBot": {"Token": "t", "ChatId": 1},
        "Db": {"Path": "data/test.db"},
        "Logging": {"Dir": "logs", "LogLevel": "DEBUG"},
    }
    with open(str(cfg_path), "w") as f:
        json.dump(minimal, f)
    settings = load_settings(str(cfg_path))
    assert settings.web.host == "0.0.0.0"
    assert settings.web.port == 8000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\wooo1\projects\systrader && python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: Implement config.py**

```python
# src/config.py
from __future__ import annotations
import json
from pydantic import BaseModel


class CybosConfig(BaseModel):
    exe_path: str


class TelegramListenerConfig(BaseModel):
    api_id: int
    api_hash: str
    phone: str
    session_name: str


class TelegramBotConfig(BaseModel):
    token: str
    chat_id: int


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class DbConfig(BaseModel):
    path: str = "data/systrader.db"


class LoggingConfig(BaseModel):
    dir: str = "logs"
    log_level: str = "INFO"


class AppSettings(BaseModel):
    cybos: CybosConfig
    telegram_listener: TelegramListenerConfig
    telegram_bot: TelegramBotConfig
    web: WebConfig = WebConfig()
    db: DbConfig = DbConfig()
    logging: LoggingConfig = LoggingConfig()


_KEY_MAP = {
    "Cybos": "cybos",
    "TelegramListener": "telegram_listener",
    "TelegramBot": "telegram_bot",
    "Web": "web",
    "Db": "db",
    "Logging": "logging",
}

_FIELD_MAP = {
    "ExePath": "exe_path",
    "ApiId": "api_id",
    "ApiHash": "api_hash",
    "Phone": "phone",
    "SessionName": "session_name",
    "Token": "token",
    "ChatId": "chat_id",
    "Host": "host",
    "Port": "port",
    "Path": "path",
    "Dir": "dir",
    "LogLevel": "log_level",
}


def _to_snake(d: dict) -> dict:
    return {_FIELD_MAP.get(k, k): v for k, v in d.items()}


def load_settings(path: str = "appsettings.json") -> AppSettings:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    converted = {}
    for key, value in raw.items():
        snake_key = _KEY_MAP.get(key, key.lower())
        if isinstance(value, dict):
            converted[snake_key] = _to_snake(value)
        else:
            converted[snake_key] = value
    return AppSettings(**converted)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Create models.py**

```python
# src/models.py
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional


class Trade(BaseModel):
    id: Optional[int] = None
    stock_code: str
    stock_name: str
    news_source: str
    news_channel: Optional[str] = None
    news_text: Optional[str] = None
    buy_price: Optional[float] = None
    buy_qty: Optional[int] = None
    buy_time: Optional[str] = None
    buy_order_price: Optional[float] = None
    sell_price: Optional[float] = None
    sell_qty: Optional[int] = None
    sell_time: Optional[str] = None
    sell_reason: Optional[str] = None
    pnl_pct: Optional[float] = None
    pnl_amount: Optional[float] = None
    highest_price: Optional[float] = None
    hold_seconds: Optional[float] = None
    status: str = "screening"
    parameter_snapshot: Optional[str] = None
    created_at: Optional[str] = None


class TradeExecution(BaseModel):
    id: Optional[int] = None
    trade_id: int
    side: str
    price: float
    quantity: int
    executed_at: str


class Tick(BaseModel):
    id: Optional[int] = None
    trade_id: int
    stock_code: str
    price: float
    volume: int
    bid_or_ask: str
    timestamp: str


class Parameter(BaseModel):
    id: Optional[int] = None
    key: str
    value: str
    updated_at: Optional[str] = None
    updated_by: str = "system"


class NewsChannel(BaseModel):
    id: Optional[int] = None
    channel_url: str
    channel_name: Optional[str] = None
    enabled: int = 1
    created_at: Optional[str] = None


class DailyStat(BaseModel):
    date: str
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl_pct: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    avg_hold_seconds: float = 0.0
    news_source_stats: Optional[str] = None


class NewsFeedItem(BaseModel):
    stock_code: str
    stock_name: str
    source: str
    category: Optional[str] = None
    text: str
    time: Optional[str] = None
    timestamp: Optional[str] = None


class SystemStatus(BaseModel):
    cybos_connected: bool
    server_type: str = ""
    engine_running: bool
    active_workers: int = 0
    account_number: str = ""
    error: Optional[str] = None
    telegram_code_pending: bool = False
```

- [ ] **Step 6: Commit**

```bash
git add src/config.py src/models.py tests/test_config.py
git commit -m "feat: add config loader and pydantic models"
```

---

### Task 4: Database & Repositories

**Files:**
- Create: `src/database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write database tests**

```python
# tests/test_database.py
import os
import pytest
from src.database import Database


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    database = Database(db_path)
    database.ensure_schema()
    return database


class TestTradeRepository:
    def test_create_trade(self, db):
        trade_id = db.trades.create(
            stock_code="A005930", stock_name="삼성전자",
            news_source="telegram", news_channel="test_ch",
            news_text="삼성전자 관련 뉴스"
        )
        assert trade_id > 0

    def test_get_trade(self, db):
        trade_id = db.trades.create(
            stock_code="A005930", stock_name="삼성전자",
            news_source="telegram"
        )
        trade = db.trades.get(trade_id)
        assert trade["stock_code"] == "A005930"
        assert trade["status"] == "screening"

    def test_list_trades_with_status_filter(self, db):
        db.trades.create(stock_code="A005930", stock_name="삼성전자", news_source="t")
        db.trades.create(stock_code="A000660", stock_name="SK하이닉스", news_source="t")
        db.trades.update(1, status="done")
        result = db.trades.list(status="screening")
        assert len(result) == 1
        assert result[0]["stock_code"] == "A000660"

    def test_update_trade_buy(self, db):
        tid = db.trades.create(stock_code="A005930", stock_name="삼성전자", news_source="t")
        db.trades.update(tid, buy_price=70000, buy_qty=14, buy_time="2026-04-11T10:00:00",
                         buy_order_price=70050, status="holding")
        trade = db.trades.get(tid)
        assert trade["buy_price"] == 70000
        assert trade["status"] == "holding"


class TestParameterRepository:
    def test_get_all_empty(self, db):
        params = db.params.get_all()
        assert params == []

    def test_upsert_and_get(self, db):
        db.params.upsert("max_holdings", "3", "system")
        params = db.params.get_all()
        assert len(params) == 1
        assert params[0]["key"] == "max_holdings"
        assert params[0]["value"] == "3"

    def test_upsert_records_history(self, db):
        db.params.upsert("max_holdings", "3", "system")
        db.params.upsert("max_holdings", "5", "user")
        history = db.params.get_history()
        assert len(history) == 1
        assert history[0]["old_value"] == "3"
        assert history[0]["new_value"] == "5"


class TestTickRepository:
    def test_insert_and_get_ticks(self, db):
        tid = db.trades.create(stock_code="A005930", stock_name="삼성전자", news_source="t")
        db.ticks.insert(tid, "A005930", 70000, 100, "buy", "2026-04-11T10:00:00.000")
        db.ticks.insert(tid, "A005930", 70050, 50, "sell", "2026-04-11T10:00:00.100")
        ticks = db.ticks.get_by_trade(tid)
        assert len(ticks) == 2
        assert ticks[0]["price"] == 70000


class TestNewsChannelRepository:
    def test_create_and_list(self, db):
        db.channels.create("https://t.me/test", "Test Channel")
        channels = db.channels.list()
        assert len(channels) == 1
        assert channels[0]["channel_name"] == "Test Channel"
        assert channels[0]["enabled"] == 1

    def test_toggle(self, db):
        db.channels.create("https://t.me/test", "Test")
        db.channels.toggle(1)
        channels = db.channels.list()
        assert channels[0]["enabled"] == 0

    def test_delete(self, db):
        db.channels.create("https://t.me/test", "Test")
        db.channels.delete(1)
        assert db.channels.list() == []


class TestExecutionRepository:
    def test_insert_and_get(self, db):
        tid = db.trades.create(stock_code="A005930", stock_name="삼성전자", news_source="t")
        db.executions.insert(tid, "BUY", 70000, 14, "2026-04-11T10:00:00")
        execs = db.executions.get_by_trade(tid)
        assert len(execs) == 1
        assert execs[0]["side"] == "BUY"


class TestDailyStatsRepository:
    def test_upsert_and_get(self, db):
        db.daily_stats.upsert("2026-04-11", total_trades=5, win_count=3,
                               loss_count=2, win_rate=0.6, total_pnl=15000)
        stats = db.daily_stats.get_range(days=30)
        assert len(stats) == 1
        assert stats[0]["total_trades"] == 5

    def test_get_summary(self, db):
        db.daily_stats.upsert("2026-04-11", total_trades=5, win_count=3,
                               loss_count=2, win_rate=0.6, total_pnl=15000,
                               avg_pnl_pct=0.5)
        summary = db.daily_stats.get_summary()
        assert summary["total_trades"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_database.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.database'`

- [ ] **Step 3: Implement database.py**

```python
# src/database.py
from __future__ import annotations
import sqlite3
import os
from typing import Optional


class TradeRepository:
    def __init__(self, db: Database):
        self._db = db

    def create(self, stock_code: str, stock_name: str, news_source: str,
               news_channel: str = None, news_text: str = None,
               parameter_snapshot: str = None) -> int:
        cur = self._db.execute(
            "INSERT INTO trades (stock_code, stock_name, news_source, news_channel, "
            "news_text, parameter_snapshot) VALUES (?, ?, ?, ?, ?, ?)",
            (stock_code, stock_name, news_source, news_channel, news_text, parameter_snapshot)
        )
        return cur.lastrowid

    def get(self, trade_id: int) -> Optional[dict]:
        return self._db.fetch_one("SELECT * FROM trades WHERE id = ?", (trade_id,))

    def list(self, status: str = None, date: str = None, limit: int = 100,
             news_source: str = None) -> list[dict]:
        query = "SELECT * FROM trades WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if date:
            query += " AND date(created_at) = ?"
            params.append(date)
        if news_source:
            query += " AND news_source = ?"
            params.append(news_source)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return self._db.fetch_all(query, tuple(params))

    def update(self, trade_id: int, **kwargs) -> None:
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [trade_id]
        self._db.execute(f"UPDATE trades SET {sets} WHERE id = ?", tuple(vals))


class ParameterRepository:
    def __init__(self, db: Database):
        self._db = db

    def get_all(self) -> list[dict]:
        return self._db.fetch_all("SELECT * FROM parameters ORDER BY key")

    def upsert(self, key: str, value: str, updated_by: str) -> None:
        existing = self._db.fetch_one("SELECT value FROM parameters WHERE key = ?", (key,))
        if existing:
            self._db.execute(
                "INSERT INTO parameter_history (key, old_value, new_value, updated_by) "
                "VALUES (?, ?, ?, ?)",
                (key, existing["value"], value, updated_by)
            )
            self._db.execute(
                "UPDATE parameters SET value = ?, updated_at = datetime('now', 'localtime'), "
                "updated_by = ? WHERE key = ?",
                (value, updated_by, key)
            )
        else:
            self._db.execute(
                "INSERT INTO parameters (key, value, updated_by) VALUES (?, ?, ?)",
                (key, value, updated_by)
            )

    def get_history(self) -> list[dict]:
        return self._db.fetch_all(
            "SELECT * FROM parameter_history ORDER BY updated_at DESC"
        )


class TickRepository:
    def __init__(self, db: Database):
        self._db = db

    def insert(self, trade_id: int, stock_code: str, price: float,
               volume: int, bid_or_ask: str, timestamp: str) -> int:
        cur = self._db.execute(
            "INSERT INTO ticks (trade_id, stock_code, price, volume, bid_or_ask, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (trade_id, stock_code, price, volume, bid_or_ask, timestamp)
        )
        return cur.lastrowid

    def get_by_trade(self, trade_id: int) -> list[dict]:
        return self._db.fetch_all(
            "SELECT * FROM ticks WHERE trade_id = ? ORDER BY timestamp", (trade_id,)
        )


class ExecutionRepository:
    def __init__(self, db: Database):
        self._db = db

    def insert(self, trade_id: int, side: str, price: float,
               quantity: int, executed_at: str) -> int:
        cur = self._db.execute(
            "INSERT INTO trade_executions (trade_id, side, price, quantity, executed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (trade_id, side, price, quantity, executed_at)
        )
        return cur.lastrowid

    def get_by_trade(self, trade_id: int) -> list[dict]:
        return self._db.fetch_all(
            "SELECT * FROM trade_executions WHERE trade_id = ? ORDER BY executed_at",
            (trade_id,)
        )


class NewsChannelRepository:
    def __init__(self, db: Database):
        self._db = db

    def list(self) -> list[dict]:
        return self._db.fetch_all("SELECT * FROM news_channels ORDER BY id")

    def create(self, channel_url: str, channel_name: str = None) -> int:
        cur = self._db.execute(
            "INSERT INTO news_channels (channel_url, channel_name) VALUES (?, ?)",
            (channel_url, channel_name)
        )
        return cur.lastrowid

    def delete(self, channel_id: int) -> None:
        self._db.execute("DELETE FROM news_channels WHERE id = ?", (channel_id,))

    def toggle(self, channel_id: int) -> None:
        self._db.execute(
            "UPDATE news_channels SET enabled = CASE WHEN enabled = 1 THEN 0 ELSE 1 END "
            "WHERE id = ?", (channel_id,)
        )


class DailyStatsRepository:
    def __init__(self, db: Database):
        self._db = db

    def upsert(self, date: str, **kwargs) -> None:
        existing = self._db.fetch_one("SELECT * FROM daily_stats WHERE date = ?", (date,))
        if existing:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            vals = list(kwargs.values()) + [date]
            self._db.execute(f"UPDATE daily_stats SET {sets} WHERE date = ?", tuple(vals))
        else:
            cols = ["date"] + list(kwargs.keys())
            placeholders = ", ".join(["?"] * len(cols))
            vals = [date] + list(kwargs.values())
            self._db.execute(
                f"INSERT INTO daily_stats ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(vals)
            )

    def get_range(self, days: int = 365, date_from: str = None,
                  date_to: str = None) -> list[dict]:
        if date_from and date_to:
            return self._db.fetch_all(
                "SELECT * FROM daily_stats WHERE date BETWEEN ? AND ? ORDER BY date DESC",
                (date_from, date_to)
            )
        return self._db.fetch_all(
            "SELECT * FROM daily_stats WHERE date >= date('now', 'localtime', ?) "
            "ORDER BY date DESC", (f"-{days} days",)
        )

    def get_summary(self, date_from: str = None, date_to: str = None,
                    source: str = None) -> dict:
        rows = self.get_range(date_from=date_from, date_to=date_to) if date_from else self.get_range()
        if not rows:
            return {"total_trades": 0, "win_count": 0, "loss_count": 0,
                    "win_rate": 0.0, "total_pnl": 0.0, "avg_pnl_pct": 0.0}
        total_trades = sum(r["total_trades"] for r in rows)
        win_count = sum(r["win_count"] for r in rows)
        loss_count = sum(r["loss_count"] for r in rows)
        total_pnl = sum(r["total_pnl"] for r in rows)
        avg_pnl = sum(r["avg_pnl_pct"] for r in rows) / len(rows) if rows else 0
        return {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": win_count / total_trades if total_trades > 0 else 0.0,
            "total_pnl": total_pnl,
            "avg_pnl_pct": avg_pnl,
        }


class Database:
    def __init__(self, path: str):
        self._path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        self.trades = TradeRepository(self)
        self.params = ParameterRepository(self)
        self.ticks = TickRepository(self)
        self.executions = ExecutionRepository(self)
        self.channels = NewsChannelRepository(self)
        self.daily_stats = DailyStatsRepository(self)

    def ensure_schema(self) -> None:
        schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
        with open(schema_path, encoding="utf-8") as f:
            self._conn.executescript(f.read())

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_database.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/database.py tests/test_database.py
git commit -m "feat: add SQLite database layer with repositories"
```

---

### Task 5: Core — EventBus & CommandQueue

**Files:**
- Create: `src/core/event_bus.py`
- Create: `src/core/command_queue.py`
- Create: `tests/test_event_bus.py`
- Create: `tests/test_command_queue.py`

- [ ] **Step 1: Write EventBus test**

```python
# tests/test_event_bus.py
import asyncio
import threading
import time
import pytest
from src.core.event_bus import EventBus


def test_subscribe_and_publish():
    bus = EventBus()
    received = []
    bus.subscribe("test", lambda data: received.append(data))
    bus.publish("test", {"msg": "hello"})
    time.sleep(0.05)
    assert len(received) == 1
    assert received[0]["msg"] == "hello"


def test_multiple_subscribers():
    bus = EventBus()
    results_a = []
    results_b = []
    bus.subscribe("evt", lambda d: results_a.append(d))
    bus.subscribe("evt", lambda d: results_b.append(d))
    bus.publish("evt", {"x": 1})
    time.sleep(0.05)
    assert len(results_a) == 1
    assert len(results_b) == 1


def test_different_event_types():
    bus = EventBus()
    a_events = []
    b_events = []
    bus.subscribe("a", lambda d: a_events.append(d))
    bus.subscribe("b", lambda d: b_events.append(d))
    bus.publish("a", {"v": 1})
    bus.publish("b", {"v": 2})
    time.sleep(0.05)
    assert len(a_events) == 1
    assert len(b_events) == 1


def test_publish_from_different_thread():
    bus = EventBus()
    received = []
    bus.subscribe("cross", lambda d: received.append(d))

    def worker():
        bus.publish("cross", {"from": "thread"})

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    time.sleep(0.05)
    assert len(received) == 1


def test_async_wait_event():
    bus = EventBus()

    async def run():
        loop = asyncio.get_event_loop()
        bus.set_async_loop(loop)

        async def publisher():
            await asyncio.sleep(0.02)
            bus.publish("async_evt", {"val": 42})

        asyncio.create_task(publisher())
        data = await asyncio.wait_for(bus.wait_event("async_evt"), timeout=1.0)
        assert data["val"] == 42

    asyncio.run(run())
```

- [ ] **Step 2: Write CommandQueue test**

```python
# tests/test_command_queue.py
import asyncio
import threading
import time
import pytest
from src.core.command_queue import CommandQueue


def test_put_and_process():
    cq = CommandQueue()

    def handler(cmd, params):
        return {"result": cmd + "_done"}

    cq.register_handler(handler)

    # Simulate FastAPI thread putting a command
    result_holder = []

    def api_thread():
        future = cq.put("test_cmd", {"a": 1})
        result_holder.append(future.result(timeout=2.0))

    t = threading.Thread(target=api_thread)
    t.start()

    # Simulate main thread processing
    time.sleep(0.02)
    cq.process()

    t.join(timeout=2.0)
    assert len(result_holder) == 1
    assert result_holder[0]["result"] == "test_cmd_done"


def test_process_empty_queue():
    cq = CommandQueue()
    cq.register_handler(lambda cmd, params: None)
    cq.process()  # should not raise


def test_handler_exception_sets_future_exception():
    cq = CommandQueue()

    def bad_handler(cmd, params):
        raise ValueError("oops")

    cq.register_handler(bad_handler)
    future = cq.put("fail", {})
    cq.process()

    with pytest.raises(ValueError, match="oops"):
        future.result(timeout=1.0)


def test_has_pending():
    cq = CommandQueue()
    cq.register_handler(lambda cmd, params: None)
    assert not cq.has_pending()
    cq.put("x", {})
    assert cq.has_pending()
    cq.process()
    assert not cq.has_pending()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_event_bus.py tests/test_command_queue.py -v`
Expected: FAIL — modules not found

- [ ] **Step 4: Implement event_bus.py**

```python
# src/core/event_bus.py
from __future__ import annotations
import asyncio
import threading
from collections import defaultdict
from typing import Callable


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._async_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = threading.Lock()
        self._async_loop: asyncio.AbstractEventLoop | None = None

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._async_loop = loop

    def subscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            subs = self._subscribers[event_type]
            if callback in subs:
                subs.remove(callback)

    def publish(self, event_type: str, data: dict) -> None:
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))
            queues = list(self._async_queues.get(event_type, []))

        for cb in callbacks:
            try:
                cb(data)
            except Exception:
                pass

        for q in queues:
            try:
                if self._async_loop and self._async_loop.is_running():
                    self._async_loop.call_soon_threadsafe(q.put_nowait, data)
                else:
                    q.put_nowait(data)
            except Exception:
                pass

    async def wait_event(self, event_type: str) -> dict:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._async_queues[event_type].append(q)
        try:
            return await q.get()
        finally:
            with self._lock:
                self._async_queues[event_type].remove(q)
```

- [ ] **Step 5: Implement command_queue.py**

```python
# src/core/command_queue.py
from __future__ import annotations
import queue
import threading
from concurrent.futures import Future
from typing import Callable, Any


class CommandQueue:
    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._handler: Callable | None = None
        self._event = threading.Event()

    def register_handler(self, handler: Callable[[str, dict], Any]) -> None:
        self._handler = handler

    def put(self, command: str, params: dict) -> Future:
        future = Future()
        self._queue.put((command, params, future))
        self._event.set()
        return future

    def has_pending(self) -> bool:
        return not self._queue.empty()

    def get_event(self) -> threading.Event:
        return self._event

    def process(self) -> None:
        while not self._queue.empty():
            try:
                command, params, future = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                result = self._handler(command, params)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
        self._event.clear()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_event_bus.py tests/test_command_queue.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/core/event_bus.py src/core/command_queue.py tests/test_event_bus.py tests/test_command_queue.py
git commit -m "feat: add EventBus and CommandQueue for thread communication"
```

---

### Task 6: Core — Logging

**Files:**
- Create: `src/core/log.py`

- [ ] **Step 1: Implement log.py**

```python
# src/core/log.py
from __future__ import annotations
import logging
import os
from collections import deque
from logging.handlers import TimedRotatingFileHandler


class LogBuffer:
    def __init__(self, maxlen: int = 1000):
        self.buffer: deque[dict] = deque(maxlen=maxlen)
        self.seq: int = 0
        self._lock = __import__("threading").Lock()

    def append(self, record: logging.LogRecord) -> None:
        with self._lock:
            self.seq += 1
            self.buffer.append({
                "seq": self.seq,
                "timestamp": record.created,
                "level": record.levelname,
                "message": record.getMessage(),
                "logger": record.name,
            })

    def get_after(self, after_seq: int) -> list[dict]:
        with self._lock:
            return [e for e in self.buffer if e["seq"] > after_seq]


class BufferHandler(logging.Handler):
    def __init__(self, log_buffer: LogBuffer):
        super().__init__()
        self.log_buffer = log_buffer

    def emit(self, record: logging.LogRecord) -> None:
        self.log_buffer.append(record)


_log_buffer: LogBuffer | None = None


def get_log_buffer() -> LogBuffer:
    global _log_buffer
    if _log_buffer is None:
        _log_buffer = LogBuffer()
    return _log_buffer


def setup_logging(log_dir: str = "logs", log_level: str = "INFO") -> LogBuffer:
    global _log_buffer
    os.makedirs(log_dir, exist_ok=True)
    _log_buffer = LogBuffer()

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # File handler — daily rotation
    file_path = os.path.join(log_dir, "systrader.log")
    file_handler = TimedRotatingFileHandler(
        file_path, when="midnight", backupCount=365, encoding="utf-8"
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Buffer handler — for /api/logs/live
    buffer_handler = BufferHandler(_log_buffer)
    buffer_handler.setFormatter(fmt)
    root.addHandler(buffer_handler)

    return _log_buffer
```

- [ ] **Step 2: Commit**

```bash
git add src/core/log.py
git commit -m "feat: add logging setup with file rotation and LogBuffer"
```

---

### Task 7: Engine — Tick Unit & BPI Calculator

**Files:**
- Create: `src/engine/tick_unit.py`
- Create: `src/engine/bpi.py`
- Create: `tests/test_tick_unit.py`
- Create: `tests/test_bpi.py`

- [ ] **Step 1: Write tick unit tests**

```python
# tests/test_tick_unit.py
from src.engine.tick_unit import get_tick_unit, round_to_tick


def test_tick_unit_below_2000():
    assert get_tick_unit(1500) == 1
    assert get_tick_unit(1) == 1
    assert get_tick_unit(1999) == 1


def test_tick_unit_2000_to_5000():
    assert get_tick_unit(2000) == 5
    assert get_tick_unit(4999) == 5


def test_tick_unit_5000_to_10000():
    assert get_tick_unit(5000) == 10
    assert get_tick_unit(9999) == 10


def test_tick_unit_10000_to_50000():
    assert get_tick_unit(10000) == 50
    assert get_tick_unit(49999) == 50


def test_tick_unit_50000_to_200000():
    assert get_tick_unit(50000) == 100
    assert get_tick_unit(199999) == 100


def test_tick_unit_200000_to_500000():
    assert get_tick_unit(200000) == 500
    assert get_tick_unit(499999) == 500


def test_tick_unit_above_500000():
    assert get_tick_unit(500000) == 1000
    assert get_tick_unit(1000000) == 1000


def test_round_to_tick_up():
    assert round_to_tick(10030, direction="up") == 10050
    assert round_to_tick(10050, direction="up") == 10050


def test_round_to_tick_down():
    assert round_to_tick(10030, direction="down") == 10000
    assert round_to_tick(10050, direction="down") == 10050
```

- [ ] **Step 2: Run tick unit tests to verify they fail**

Run: `python -m pytest tests/test_tick_unit.py -v`
Expected: FAIL

- [ ] **Step 3: Implement tick_unit.py**

```python
# src/engine/tick_unit.py

_TICK_TABLE = [
    (2_000, 1),
    (5_000, 5),
    (10_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
]
_DEFAULT_TICK = 1_000


def get_tick_unit(price: int | float) -> int:
    for threshold, unit in _TICK_TABLE:
        if price < threshold:
            return unit
    return _DEFAULT_TICK


def round_to_tick(price: int | float, direction: str = "up") -> int:
    unit = get_tick_unit(price)
    if direction == "up":
        return int(((price + unit - 1) // unit) * unit)
    else:
        return int((price // unit) * unit)
```

- [ ] **Step 4: Run tick unit tests to verify they pass**

Run: `python -m pytest tests/test_tick_unit.py -v`
Expected: PASS

- [ ] **Step 5: Write BPI tests**

```python
# tests/test_bpi.py
from src.engine.bpi import BpiCalculator


def test_empty_bpi():
    bpi = BpiCalculator(short_window=3, long_window=5)
    assert bpi.short == 0.5
    assert bpi.long == 0.5


def test_all_buy_ticks():
    bpi = BpiCalculator(short_window=3, long_window=5)
    for _ in range(5):
        bpi.add(is_buy=True)
    assert bpi.short == 1.0
    assert bpi.long == 1.0


def test_all_sell_ticks():
    bpi = BpiCalculator(short_window=3, long_window=5)
    for _ in range(5):
        bpi.add(is_buy=False)
    assert bpi.short == 0.0
    assert bpi.long == 0.0


def test_mixed_ticks():
    bpi = BpiCalculator(short_window=4, long_window=4)
    bpi.add(is_buy=True)
    bpi.add(is_buy=False)
    bpi.add(is_buy=True)
    bpi.add(is_buy=False)
    assert bpi.short == 0.5
    assert bpi.long == 0.5


def test_window_sliding():
    bpi = BpiCalculator(short_window=3, long_window=5)
    # Fill: B B B B B
    for _ in range(5):
        bpi.add(is_buy=True)
    # Add sells: short=[B, S, S], long=[B, B, B, S, S]
    bpi.add(is_buy=False)
    bpi.add(is_buy=False)
    assert abs(bpi.short - 1 / 3) < 0.01
    assert abs(bpi.long - 3 / 5) < 0.01


def test_reset():
    bpi = BpiCalculator(short_window=3, long_window=5)
    for _ in range(5):
        bpi.add(is_buy=True)
    bpi.reset()
    assert bpi.short == 0.5
    assert bpi.long == 0.5


def test_sell_signal():
    bpi = BpiCalculator(short_window=3, long_window=5)
    # Fill long with buys
    for _ in range(5):
        bpi.add(is_buy=True)
    # Shift short to sells
    bpi.add(is_buy=False)
    bpi.add(is_buy=False)
    bpi.add(is_buy=False)
    # short=0.0, long=2/5=0.4
    assert bpi.is_sell_signal(threshold=0.4)


def test_no_sell_signal_when_short_above_long():
    bpi = BpiCalculator(short_window=3, long_window=5)
    for _ in range(5):
        bpi.add(is_buy=True)
    assert not bpi.is_sell_signal(threshold=0.4)
```

- [ ] **Step 6: Run BPI tests to verify they fail**

Run: `python -m pytest tests/test_bpi.py -v`
Expected: FAIL

- [ ] **Step 7: Implement bpi.py**

```python
# src/engine/bpi.py
from __future__ import annotations
from collections import deque


class BpiCalculator:
    def __init__(self, short_window: int = 10, long_window: int = 30):
        self._short_window = short_window
        self._long_window = long_window
        self._short: deque[bool] = deque(maxlen=short_window)
        self._long: deque[bool] = deque(maxlen=long_window)

    def add(self, is_buy: bool) -> None:
        self._short.append(is_buy)
        self._long.append(is_buy)

    @property
    def short(self) -> float:
        if not self._short:
            return 0.5
        return sum(self._short) / len(self._short)

    @property
    def long(self) -> float:
        if not self._long:
            return 0.5
        return sum(self._long) / len(self._long)

    def is_sell_signal(self, threshold: float) -> bool:
        return self.short <= self.long and self.short < threshold

    def reset(self) -> None:
        self._short.clear()
        self._long.clear()
```

- [ ] **Step 8: Run BPI tests to verify they pass**

Run: `python -m pytest tests/test_bpi.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/engine/tick_unit.py src/engine/bpi.py tests/test_tick_unit.py tests/test_bpi.py
git commit -m "feat: add tick unit calculator and BPI calculator"
```

---

### Task 8: Engine — Screener

**Files:**
- Create: `src/engine/screener.py`
- Create: `tests/test_screener.py`

- [ ] **Step 1: Write screener tests**

```python
# tests/test_screener.py
import pytest
from src.engine.screener import Screener


@pytest.fixture
def screener():
    return Screener(
        max_holdings=3,
        min_market_cap=50_000_000_000,
        max_market_cap=1_000_000_000_000,
        min_change_pct=5.0,
        max_change_pct=28.0,
    )


def test_passes_valid_stock(screener):
    result = screener.check(
        market_cap=100_000_000_000,
        change_pct=10.0,
        current_price=50000,
        upper_limit_price=65000,
        current_holdings=0,
    )
    assert result.passed is True


def test_fails_too_many_holdings(screener):
    result = screener.check(
        market_cap=100_000_000_000,
        change_pct=10.0,
        current_price=50000,
        upper_limit_price=65000,
        current_holdings=3,
    )
    assert result.passed is False
    assert result.reason == "max_holdings"


def test_fails_market_cap_too_low(screener):
    result = screener.check(
        market_cap=10_000_000_000,
        change_pct=10.0,
        current_price=50000,
        upper_limit_price=65000,
        current_holdings=0,
    )
    assert result.passed is False
    assert result.reason == "min_market_cap"


def test_fails_market_cap_too_high(screener):
    result = screener.check(
        market_cap=2_000_000_000_000,
        change_pct=10.0,
        current_price=50000,
        upper_limit_price=65000,
        current_holdings=0,
    )
    assert result.passed is False
    assert result.reason == "max_market_cap"


def test_fails_change_pct_too_low(screener):
    result = screener.check(
        market_cap=100_000_000_000,
        change_pct=2.0,
        current_price=50000,
        upper_limit_price=65000,
        current_holdings=0,
    )
    assert result.passed is False
    assert result.reason == "min_change_pct"


def test_fails_change_pct_too_high(screener):
    result = screener.check(
        market_cap=100_000_000_000,
        change_pct=29.0,
        current_price=50000,
        upper_limit_price=65000,
        current_holdings=0,
    )
    assert result.passed is False
    assert result.reason == "max_change_pct"


def test_fails_price_near_upper_limit(screener):
    result = screener.check(
        market_cap=100_000_000_000,
        change_pct=10.0,
        current_price=64000,
        upper_limit_price=65000,
        current_holdings=0,
    )
    assert result.passed is False
    assert result.reason == "near_upper_limit"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_screener.py -v`
Expected: FAIL

- [ ] **Step 3: Implement screener.py**

```python
# src/engine/screener.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ScreenResult:
    passed: bool
    reason: str = ""


class Screener:
    def __init__(self, max_holdings: int, min_market_cap: int, max_market_cap: int,
                 min_change_pct: float, max_change_pct: float):
        self.max_holdings = max_holdings
        self.min_market_cap = min_market_cap
        self.max_market_cap = max_market_cap
        self.min_change_pct = min_change_pct
        self.max_change_pct = max_change_pct

    def check(self, market_cap: int, change_pct: float, current_price: float,
              upper_limit_price: float, current_holdings: int) -> ScreenResult:
        if current_holdings >= self.max_holdings:
            return ScreenResult(False, "max_holdings")
        if market_cap < self.min_market_cap:
            return ScreenResult(False, "min_market_cap")
        if market_cap > self.max_market_cap:
            return ScreenResult(False, "max_market_cap")
        if change_pct < self.min_change_pct:
            return ScreenResult(False, "min_change_pct")
        if change_pct > self.max_change_pct:
            return ScreenResult(False, "max_change_pct")
        if current_price >= upper_limit_price * 0.98:
            return ScreenResult(False, "near_upper_limit")
        return ScreenResult(True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_screener.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/engine/screener.py tests/test_screener.py
git commit -m "feat: add stock screener with filter criteria"
```

---

### Task 9: Engine — Worker State Machine

**Files:**
- Create: `src/engine/worker.py`
- Create: `tests/test_worker.py`

- [ ] **Step 1: Write worker tests**

```python
# tests/test_worker.py
import time
import pytest
from unittest.mock import MagicMock
from src.engine.worker import StockWorker, WorkerState


@pytest.fixture
def params():
    return {
        "entry_up_ticks": 3,
        "entry_buy_ratio": 0.6,
        "entry_timeout_sec": 60,
        "buy_tick_offset": 1,
        "bet_amount": 1_000_000,
        "fill_timeout_sec": 10,
        "bpi_short_window": 10,
        "bpi_long_window": 30,
        "bpi_sell_threshold": 0.4,
        "stoploss_pct": -0.03,
        "maxdrop_pct": -0.02,
        "max_hold_sec": 300,
        "vi_detect_sec": 3.0,
    }


@pytest.fixture
def worker(params):
    on_order = MagicMock()
    on_state_change = MagicMock()
    w = StockWorker(
        stock_code="A005930", stock_name="삼성전자",
        news_source="telegram", news_text="test",
        params=params, on_order=on_order, on_state_change=on_state_change,
    )
    return w


def make_tick(price, bid_or_ask="buy", volume=100):
    return {"price": price, "volume": volume, "bid_or_ask": bid_or_ask,
            "timestamp": time.time()}


class TestScreeningPhase:
    def test_initial_state_is_screening(self, worker):
        assert worker.state == WorkerState.SCREENING

    def test_entry_on_consecutive_up_ticks(self, worker):
        # 5 consecutive up ticks with all buys → should trigger buy
        worker.on_tick(make_tick(10000))
        worker.on_tick(make_tick(10050))
        worker.on_tick(make_tick(10100))
        worker.on_tick(make_tick(10150))
        worker.on_tick(make_tick(10200))
        assert worker.state == WorkerState.BUYING

    def test_no_entry_without_enough_up_ticks(self, worker):
        worker.on_tick(make_tick(10000))
        worker.on_tick(make_tick(10050))
        worker.on_tick(make_tick(10000))  # down
        assert worker.state == WorkerState.SCREENING

    def test_no_entry_without_buy_ratio(self, worker):
        # Up ticks but all sells → buy ratio too low
        worker.on_tick(make_tick(10000, "sell"))
        worker.on_tick(make_tick(10050, "sell"))
        worker.on_tick(make_tick(10100, "sell"))
        worker.on_tick(make_tick(10150, "sell"))
        assert worker.state == WorkerState.SCREENING

    def test_entry_timeout_cancels(self, worker, params):
        params["entry_timeout_sec"] = 0  # immediate timeout
        worker.params = params
        worker._screen_start = time.time() - 1
        worker.on_tick(make_tick(10000))
        assert worker.state == WorkerState.CANCELLED


class TestHoldingPhase:
    def _enter_holding(self, worker):
        """Helper: transition worker to Holding state"""
        worker.state = WorkerState.HOLDING
        worker.buy_price = 10000
        worker.buy_qty = 100
        worker.highest_price = 10000
        worker._hold_start = time.time()
        worker._last_tick_time = time.time()
        worker._init_bpi()

    def test_stoploss_triggers_sell(self, worker):
        self._enter_holding(worker)
        worker.on_tick(make_tick(9600))  # -4% < -3% stoploss
        assert worker.state == WorkerState.SELLING

    def test_maxdrop_triggers_sell(self, worker):
        self._enter_holding(worker)
        worker.highest_price = 11000
        worker.on_tick(make_tick(10700))  # (10700-11000)/11000 = -2.7% < -2%
        assert worker.state == WorkerState.SELLING

    def test_timeout_triggers_sell(self, worker, params):
        self._enter_holding(worker)
        params["max_hold_sec"] = 0
        worker.params = params
        worker._hold_start = time.time() - 1
        worker.on_tick(make_tick(10000))
        assert worker.state == WorkerState.SELLING

    def test_bpi_reversal_triggers_sell(self, worker):
        self._enter_holding(worker)
        # Fill BPI long with buys, then short with sells
        for _ in range(30):
            worker.bpi.add(is_buy=True)
        for _ in range(10):
            worker.bpi.add(is_buy=False)
        # Now short=0.0, long has mix, short < long and short < threshold
        worker.on_tick(make_tick(10000, "sell"))
        assert worker.state == WorkerState.SELLING

    def test_updates_highest_price(self, worker):
        self._enter_holding(worker)
        worker.on_tick(make_tick(10500))
        assert worker.highest_price == 10500

    def test_vi_detection_resets_bpi(self, worker, params):
        self._enter_holding(worker)
        params["vi_detect_sec"] = 0.01
        worker.params = params
        worker._last_tick_time = time.time() - 1  # no tick for 1 sec
        # Only stoploss should be checked during VI
        worker.on_tick(make_tick(10000))
        assert len(worker.bpi._short) == 0  # BPI was reset


class TestFillCallback:
    def test_buy_fill_transitions_to_holding(self, worker):
        worker.state = WorkerState.BUYING
        worker.on_fill(side="BUY", price=10050, quantity=99)
        assert worker.state == WorkerState.HOLDING
        assert worker.buy_price == 10050
        assert worker.buy_qty == 99

    def test_sell_fill_transitions_to_done(self, worker):
        worker.state = WorkerState.SELLING
        worker.buy_price = 10000
        worker.buy_qty = 100
        worker._hold_start = time.time() - 10
        worker.on_fill(side="SELL", price=10300, quantity=100)
        assert worker.state == WorkerState.DONE
        assert worker.pnl_pct == pytest.approx(0.03, abs=0.001)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_worker.py -v`
Expected: FAIL

- [ ] **Step 3: Implement worker.py**

```python
# src/engine/worker.py
from __future__ import annotations
import enum
import logging
import time
from typing import Callable, Optional
from src.engine.bpi import BpiCalculator
from src.engine.tick_unit import get_tick_unit

log = logging.getLogger(__name__)


class WorkerState(str, enum.Enum):
    SCREENING = "screening"
    BUYING = "buying"
    HOLDING = "holding"
    SELLING = "selling"
    DONE = "done"
    CANCELLED = "cancelled"


class StockWorker:
    def __init__(self, stock_code: str, stock_name: str, news_source: str,
                 news_text: str, params: dict,
                 on_order: Callable, on_state_change: Callable):
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.news_source = news_source
        self.news_text = news_text
        self.params = params
        self._on_order = on_order
        self._on_state_change = on_state_change

        self.state = WorkerState.SCREENING
        self.trade_id: Optional[int] = None
        self.buy_price: float = 0
        self.buy_qty: int = 0
        self.buy_order_price: float = 0
        self.sell_price: float = 0
        self.sell_qty: int = 0
        self.sell_reason: str = ""
        self.highest_price: float = 0
        self.pnl_pct: float = 0
        self.pnl_amount: float = 0
        self.hold_seconds: float = 0

        self.bpi: Optional[BpiCalculator] = None
        self._screen_start = time.time()
        self._hold_start: float = 0
        self._hold_paused: float = 0
        self._last_tick_time: float = time.time()
        self._ticks: list[dict] = []
        self._consecutive_up: int = 0
        self._last_price: float = 0
        self._order_num: Optional[int] = None

    def _set_state(self, new_state: WorkerState) -> None:
        old = self.state
        self.state = new_state
        self._on_state_change(self, old, new_state)

    def _init_bpi(self) -> None:
        self.bpi = BpiCalculator(
            short_window=self.params["bpi_short_window"],
            long_window=self.params["bpi_long_window"],
        )

    def on_tick(self, tick: dict) -> None:
        price = tick["price"]
        self._ticks.append(tick)

        if self.state == WorkerState.SCREENING:
            self._handle_screening(tick, price)
        elif self.state == WorkerState.HOLDING:
            self._handle_holding(tick, price)

        self._last_tick_time = time.time()
        self._last_price = price

    def _handle_screening(self, tick: dict, price: float) -> None:
        # Check timeout
        if time.time() - self._screen_start > self.params["entry_timeout_sec"]:
            self._set_state(WorkerState.CANCELLED)
            return

        # Track consecutive up ticks
        if self._last_price > 0 and price > self._last_price:
            self._consecutive_up += 1
        elif self._last_price > 0 and price < self._last_price:
            self._consecutive_up = 0

        # Check buy ratio
        buy_count = sum(1 for t in self._ticks if t["bid_or_ask"] == "buy")
        buy_ratio = buy_count / len(self._ticks) if self._ticks else 0

        if (self._consecutive_up >= self.params["entry_up_ticks"]
                and buy_ratio >= self.params["entry_buy_ratio"]):
            self._place_buy_order(price)

    def _place_buy_order(self, current_price: float) -> None:
        tick_unit = get_tick_unit(current_price)
        order_price = int(current_price + tick_unit * self.params["buy_tick_offset"])
        qty = self.params["bet_amount"] // order_price
        if qty <= 0:
            self._set_state(WorkerState.CANCELLED)
            return
        self.buy_order_price = order_price
        self._set_state(WorkerState.BUYING)
        self._on_order("BUY", self.stock_code, qty, order_price)

    def _handle_holding(self, tick: dict, price: float) -> None:
        self.highest_price = max(self.highest_price, price)

        # VI detection
        vi_detected = (time.time() - self._last_tick_time) > self.params["vi_detect_sec"]
        if vi_detected:
            self.bpi.reset()
            self._hold_paused += time.time() - self._last_tick_time
            # Only check stoploss during VI
            pnl_pct = (price - self.buy_price) / self.buy_price
            if pnl_pct <= self.params["stoploss_pct"]:
                self._place_sell_order(price, "stoploss")
            return

        # Add to BPI
        is_buy = tick["bid_or_ask"] == "buy"
        self.bpi.add(is_buy)

        # Calculate metrics
        pnl_pct = (price - self.buy_price) / self.buy_price
        drop_pct = (price - self.highest_price) / self.highest_price if self.highest_price > 0 else 0
        hold_time = time.time() - self._hold_start - self._hold_paused

        # Check exit signals (priority order)
        if pnl_pct <= self.params["stoploss_pct"]:
            self._place_sell_order(price, "stoploss")
        elif drop_pct <= self.params["maxdrop_pct"]:
            self._place_sell_order(price, "maxdrop")
        elif self.bpi.is_sell_signal(self.params["bpi_sell_threshold"]):
            self._place_sell_order(price, "bpi_reversal")
        elif hold_time >= self.params["max_hold_sec"]:
            self._place_sell_order(price, "timeout")

    def _place_sell_order(self, price: float, reason: str) -> None:
        self.sell_reason = reason
        self._set_state(WorkerState.SELLING)
        self._on_order("SELL_MARKET", self.stock_code, self.buy_qty, 0)

    def on_fill(self, side: str, price: float, quantity: int) -> None:
        if side == "BUY" and self.state == WorkerState.BUYING:
            self.buy_price = price
            self.buy_qty = quantity
            self.highest_price = price
            self._hold_start = time.time()
            self._hold_paused = 0
            self._last_tick_time = time.time()
            self._init_bpi()
            self._set_state(WorkerState.HOLDING)
        elif side == "SELL" and self.state == WorkerState.SELLING:
            self.sell_price = price
            self.sell_qty = quantity
            self.hold_seconds = time.time() - self._hold_start - self._hold_paused
            self.pnl_pct = (self.sell_price - self.buy_price) / self.buy_price
            self.pnl_amount = (self.sell_price - self.buy_price) * self.sell_qty
            self._set_state(WorkerState.DONE)

    def cancel(self, reason: str = "") -> None:
        self.sell_reason = reason
        self._set_state(WorkerState.CANCELLED)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_worker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/engine/worker.py tests/test_worker.py
git commit -m "feat: add StockWorker state machine with entry/exit logic"
```

---

### Task 10: Engine — TradingEngine

**Files:**
- Create: `src/engine/trading_engine.py`

- [ ] **Step 1: Implement trading_engine.py**

```python
# src/engine/trading_engine.py
from __future__ import annotations
import json
import logging
import time
from typing import Optional, Callable
from src.engine.worker import StockWorker, WorkerState
from src.engine.screener import Screener
from src.database import Database
from src.core.event_bus import EventBus

log = logging.getLogger(__name__)

PARAM_DEFAULTS = {
    "max_holdings": "3",
    "min_market_cap": "50000000000",
    "max_market_cap": "1000000000000",
    "min_change_pct": "5.0",
    "max_change_pct": "28.0",
    "entry_up_ticks": "3",
    "entry_timeout_sec": "60",
    "entry_buy_ratio": "0.6",
    "buy_tick_offset": "1",
    "bet_amount": "1000000",
    "fill_timeout_sec": "10",
    "bpi_short_window": "10",
    "bpi_long_window": "30",
    "bpi_sell_threshold": "0.4",
    "stoploss_pct": "-0.03",
    "maxdrop_pct": "-0.02",
    "max_hold_sec": "300",
    "vi_detect_sec": "3.0",
}


class TradingEngine:
    def __init__(self, db: Database, event_bus: EventBus,
                 order_func: Callable, stock_info_func: Callable,
                 subscribe_tick_func: Callable, unsubscribe_tick_func: Callable):
        self.db = db
        self.event_bus = event_bus
        self._order_func = order_func
        self._stock_info_func = stock_info_func
        self._subscribe_tick = subscribe_tick_func
        self._unsubscribe_tick = unsubscribe_tick_func
        self.workers: dict[str, StockWorker] = {}
        self.running = False
        self._params: dict = {}

    def start(self) -> None:
        self._load_params()
        self._ensure_default_params()
        self.running = True
        log.info("Trading engine started")

    def stop(self) -> None:
        self.running = False
        for code in list(self.workers.keys()):
            worker = self.workers[code]
            if worker.state in (WorkerState.SCREENING,):
                worker.cancel("engine_stop")
                self._unsubscribe_tick(code)
        log.info("Trading engine stopped")

    def _load_params(self) -> None:
        rows = self.db.params.get_all()
        self._params = {r["key"]: r["value"] for r in rows}

    def _ensure_default_params(self) -> None:
        for key, default in PARAM_DEFAULTS.items():
            if key not in self._params:
                self.db.params.upsert(key, default, "system")
                self._params[key] = default

    def get_param(self, key: str) -> str:
        return self._params.get(key, PARAM_DEFAULTS.get(key, ""))

    def get_typed_params(self) -> dict:
        int_keys = {"max_holdings", "min_market_cap", "max_market_cap",
                     "entry_up_ticks", "entry_timeout_sec", "buy_tick_offset",
                     "bet_amount", "fill_timeout_sec", "bpi_short_window",
                     "bpi_long_window", "max_hold_sec"}
        float_keys = {"min_change_pct", "max_change_pct", "entry_buy_ratio",
                       "bpi_sell_threshold", "stoploss_pct", "maxdrop_pct",
                       "vi_detect_sec"}
        result = {}
        for key in PARAM_DEFAULTS:
            val = self.get_param(key)
            if key in int_keys:
                result[key] = int(val)
            elif key in float_keys:
                result[key] = float(val)
            else:
                result[key] = val
        return result

    def on_news(self, news_data: dict) -> None:
        if not self.running:
            return
        code = news_data.get("code", "")
        name = news_data.get("name", "")
        if not code or code in self.workers:
            return

        params = self.get_typed_params()
        # Get stock info for screening
        info = self._stock_info_func(code)
        if not info:
            log.warning(f"Stock info not available for {code}")
            return

        screener = Screener(
            max_holdings=params["max_holdings"],
            min_market_cap=params["min_market_cap"],
            max_market_cap=params["max_market_cap"],
            min_change_pct=params["min_change_pct"],
            max_change_pct=params["max_change_pct"],
        )

        holding_count = sum(1 for w in self.workers.values()
                           if w.state in (WorkerState.HOLDING, WorkerState.BUYING))
        result = screener.check(
            market_cap=info["market_cap"],
            change_pct=info["change_pct"],
            current_price=info["current_price"],
            upper_limit_price=info["upper_limit_price"],
            current_holdings=holding_count,
        )

        if not result.passed:
            log.info(f"Screener rejected {code} ({name}): {result.reason}")
            return

        # Create trade record
        trade_id = self.db.trades.create(
            stock_code=code, stock_name=name,
            news_source=news_data.get("source", ""),
            news_channel=news_data.get("channel", ""),
            news_text=news_data.get("title", ""),
            parameter_snapshot=json.dumps(params),
        )

        worker = StockWorker(
            stock_code=code, stock_name=name,
            news_source=news_data.get("source", ""),
            news_text=news_data.get("title", ""),
            params=params,
            on_order=self._handle_order,
            on_state_change=self._handle_state_change,
        )
        worker.trade_id = trade_id
        self.workers[code] = worker

        # Subscribe to real-time ticks
        self._subscribe_tick(code)
        log.info(f"Worker created for {code} ({name}), trade_id={trade_id}")
        self.event_bus.publish("worker_state", {
            "code": code, "name": name, "state": "screening", "trade_id": trade_id
        })

    def on_tick(self, code: str, tick_data: dict) -> None:
        worker = self.workers.get(code)
        if not worker:
            return
        # Save tick to DB
        if worker.trade_id:
            self.db.ticks.insert(
                worker.trade_id, code, tick_data["price"],
                tick_data["volume"], tick_data["bid_or_ask"],
                tick_data.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%S"))
            )
        worker.on_tick(tick_data)

    def on_fill(self, code: str, side: str, price: float, quantity: int) -> None:
        worker = self.workers.get(code)
        if not worker:
            return
        # Record execution
        if worker.trade_id:
            self.db.executions.insert(
                worker.trade_id, side, price, quantity,
                time.strftime("%Y-%m-%dT%H:%M:%S")
            )
        worker.on_fill(side, price, quantity)

    def _handle_order(self, order_type: str, code: str, qty: int, price: int) -> None:
        try:
            self._order_func(order_type, code, qty, price)
        except Exception as e:
            log.error(f"Order failed for {code}: {e}")
            worker = self.workers.get(code)
            if worker:
                worker.cancel(f"order_error: {e}")

    def _handle_state_change(self, worker: StockWorker,
                              old: WorkerState, new: WorkerState) -> None:
        log.info(f"Worker {worker.stock_code}: {old.value} → {new.value}")

        self.event_bus.publish("worker_state", {
            "code": worker.stock_code, "name": worker.stock_name,
            "state": new.value, "trade_id": worker.trade_id,
        })

        if new == WorkerState.HOLDING and worker.trade_id:
            self.db.trades.update(worker.trade_id,
                buy_price=worker.buy_price, buy_qty=worker.buy_qty,
                buy_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                buy_order_price=worker.buy_order_price,
                highest_price=worker.buy_price, status="holding")
            self.event_bus.publish("buy_filled", {
                "code": worker.stock_code, "name": worker.stock_name,
                "price": worker.buy_price, "qty": worker.buy_qty,
                "trade_id": worker.trade_id,
            })

        elif new == WorkerState.DONE and worker.trade_id:
            self.db.trades.update(worker.trade_id,
                sell_price=worker.sell_price, sell_qty=worker.sell_qty,
                sell_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                sell_reason=worker.sell_reason,
                pnl_pct=worker.pnl_pct, pnl_amount=worker.pnl_amount,
                highest_price=worker.highest_price,
                hold_seconds=worker.hold_seconds, status="done")
            self.event_bus.publish("sell_filled", {
                "code": worker.stock_code, "name": worker.stock_name,
                "price": worker.sell_price, "qty": worker.sell_qty,
                "pnl_pct": worker.pnl_pct, "pnl_amount": worker.pnl_amount,
                "reason": worker.sell_reason, "trade_id": worker.trade_id,
            })
            self.event_bus.publish("trade_done", {
                "code": worker.stock_code, "trade_id": worker.trade_id,
                "pnl_pct": worker.pnl_pct,
            })
            self._unsubscribe_tick(worker.stock_code)

        elif new == WorkerState.CANCELLED and worker.trade_id:
            self.db.trades.update(worker.trade_id,
                sell_reason=worker.sell_reason, status="cancelled")
            self._unsubscribe_tick(worker.stock_code)

    @property
    def active_worker_count(self) -> int:
        return sum(1 for w in self.workers.values()
                   if w.state not in (WorkerState.DONE, WorkerState.CANCELLED))
```

- [ ] **Step 2: Commit**

```bash
git add src/engine/trading_engine.py
git commit -m "feat: add TradingEngine orchestrator with worker management"
```

---

### Task 11: COM Wrappers

**Files:**
- Create: `src/com/connection.py`
- Create: `src/com/code.py`
- Create: `src/com/stock.py`
- Create: `src/com/order.py`
- Create: `src/com/account.py`

- [ ] **Step 1: Implement connection.py**

```python
# src/com/connection.py
from __future__ import annotations
import logging
import time
import win32com.client
import pythoncom

log = logging.getLogger(__name__)


class CybosConnection:
    def __init__(self):
        self._cybos = win32com.client.Dispatch("CpUtil.CpCybos")

    @property
    def is_connected(self) -> bool:
        return self._cybos.IsConnect == 1

    def remaining_count(self, limit_type: int) -> int:
        """limit_type: 0=non-trade, 1=trade"""
        return self._cybos.GetLimitRemainCount(limit_type)

    def wait_if_limited(self, limit_type: int) -> None:
        while self.remaining_count(limit_type) <= 0:
            log.debug(f"API rate limited (type={limit_type}), waiting...")
            pythoncom.PumpWaitingMessages()
            time.sleep(0.2)

    def get_server_type(self) -> str:
        """0=unknown, 1=cybos, 2=HTS normal"""
        return str(self._cybos.GetStockMarketKind("A005930"))
```

- [ ] **Step 2: Implement code.py**

```python
# src/com/code.py
from __future__ import annotations
import logging
import win32com.client

log = logging.getLogger(__name__)


class CodeManager:
    def __init__(self):
        self._stock_code = win32com.client.Dispatch("CpUtil.CpStockCode")
        self._code_mgr = win32com.client.Dispatch("CpUtil.CpCodeMgr")
        self._name_to_code: dict[str, str] = {}
        self._code_to_name: dict[str, str] = {}

    def load_stock_list(self) -> None:
        """Load all KOSPI + KOSDAQ stock codes and names into cache."""
        count = 0
        for market in (1, 2):  # 1=KOSPI, 2=KOSDAQ
            codes = self._code_mgr.GetStockListByMarket(market)
            for code in codes:
                name = self._code_mgr.CodeToName(code)
                self._name_to_code[name] = code
                self._code_to_name[code] = name
                count += 1
        log.info(f"Loaded {count} stock codes")

    def name_to_code(self, name: str) -> str | None:
        return self._name_to_code.get(name)

    def code_to_name(self, code: str) -> str | None:
        return self._code_to_name.get(code)

    def all_stocks(self) -> list[tuple[str, str]]:
        """Returns list of (name, code) tuples."""
        return list(self._name_to_code.items())

    def get_section_kind(self, code: str) -> int:
        """Get market section. 1=KOSPI, 2=KOSDAQ"""
        return self._code_mgr.GetStockSectionKind(code)
```

- [ ] **Step 3: Implement stock.py**

```python
# src/com/stock.py
from __future__ import annotations
import logging
import time
import win32com.client
import pythoncom
from src.com.connection import CybosConnection

log = logging.getLogger(__name__)


class StockMst:
    """Single stock master data (BlockRequest)."""

    def __init__(self, connection: CybosConnection):
        self._conn = connection

    def request(self, code: str) -> dict | None:
        self._conn.wait_if_limited(0)
        obj = win32com.client.Dispatch("DsCbo1.StockMst")
        obj.SetInputValue(0, code)
        ret = obj.BlockRequest()
        if ret != 0:
            log.error(f"StockMst BlockRequest failed: {ret}")
            return None
        return {
            "code": code,
            "name": obj.GetHeaderValue(1),
            "current_price": obj.GetHeaderValue(11),
            "diff": obj.GetHeaderValue(12),
            "change_pct": obj.GetHeaderValue(13),
            "volume": obj.GetHeaderValue(18),
            "market_cap": obj.GetHeaderValue(23),
            "upper_limit_price": obj.GetHeaderValue(5),
            "lower_limit_price": obj.GetHeaderValue(6),
        }


class StockCurHandler:
    """Handler for real-time tick events."""
    callbacks: dict[str, callable] = {}

    def OnReceived(self):
        code = self._obj.GetHeaderValue(0)
        data = {
            "code": code,
            "price": self._obj.GetHeaderValue(13),
            "volume": self._obj.GetHeaderValue(17),
            "bid_or_ask": "buy" if self._obj.GetHeaderValue(14) == ord("2") else "sell",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.") + f"{time.time() % 1:.3f}"[2:],
        }
        cb = StockCurHandler.callbacks.get(code)
        if cb:
            cb(code, data)


class StockCurManager:
    """Manages multiple StockCur subscriptions."""

    def __init__(self, on_tick: callable):
        self._on_tick = on_tick
        self._subscriptions: dict[str, object] = {}

    def subscribe(self, code: str) -> None:
        if code in self._subscriptions:
            return
        StockCurHandler.callbacks[code] = self._on_tick
        obj = win32com.client.DispatchWithEvents("Dscbo1.StockCur", StockCurHandler)
        obj.SetInputValue(0, code)
        obj.Subscribe()
        self._subscriptions[code] = obj
        log.info(f"Subscribed to StockCur: {code}")

    def unsubscribe(self, code: str) -> None:
        obj = self._subscriptions.pop(code, None)
        if obj:
            obj.Unsubscribe()
            StockCurHandler.callbacks.pop(code, None)
            log.info(f"Unsubscribed from StockCur: {code}")

    def unsubscribe_all(self) -> None:
        for code in list(self._subscriptions.keys()):
            self.unsubscribe(code)


class MarketEye:
    """Batch quote request for multiple stocks."""

    def __init__(self, connection: CybosConnection):
        self._conn = connection

    def request(self, codes: list[str], fields: list[int] = None) -> list[dict]:
        if not codes:
            return []
        if fields is None:
            fields = [0, 4, 5, 6, 11, 12, 13, 18, 20]  # code, name, upper, lower, price, diff, pct, vol, mktcap
        self._conn.wait_if_limited(0)
        obj = win32com.client.Dispatch("CpSysDib.MarketEye")
        obj.SetInputValue(0, fields)
        obj.SetInputValue(1, codes)
        ret = obj.BlockRequest()
        if ret != 0:
            log.error(f"MarketEye BlockRequest failed: {ret}")
            return []
        count = obj.GetHeaderValue(2)
        results = []
        for i in range(count):
            row = {}
            for j, field_id in enumerate(fields):
                row[field_id] = obj.GetDataValue(j, i)
            results.append(row)
        return results
```

- [ ] **Step 4: Implement order.py**

```python
# src/com/order.py
from __future__ import annotations
import logging
import win32com.client
from src.com.connection import CybosConnection

log = logging.getLogger(__name__)


class CybosOrder:
    def __init__(self, connection: CybosConnection, account: str, goods_code: str):
        self._conn = connection
        self._account = account
        self._goods_code = goods_code

    def buy_limit(self, code: str, qty: int, price: int) -> dict:
        """Limit buy order. Returns {"order_num": int}."""
        self._conn.wait_if_limited(1)
        obj = win32com.client.Dispatch("CpTrade.CpTd0311")
        obj.SetInputValue(0, "2")               # buy
        obj.SetInputValue(1, self._account)
        obj.SetInputValue(2, self._goods_code)
        obj.SetInputValue(3, code)
        obj.SetInputValue(4, qty)
        obj.SetInputValue(5, price)
        obj.SetInputValue(7, "0")               # condition: default
        obj.SetInputValue(8, "01")              # price type: normal

        ret = obj.BlockRequest()
        if ret != 0:
            raise RuntimeError(f"Buy BlockRequest failed: ret={ret}")
        status = obj.GetDibStatus()
        msg = obj.GetDibMsg1()
        if status != 0:
            raise RuntimeError(f"Buy order failed: status={status} msg={msg}")
        order_num = obj.GetHeaderValue(8)
        log.info(f"Buy order placed: {code} {qty}@{price}, order_num={order_num}")
        return {"order_num": order_num}

    def sell_market(self, code: str, qty: int) -> dict:
        """Market sell order. Returns {"order_num": int}."""
        self._conn.wait_if_limited(1)
        obj = win32com.client.Dispatch("CpTrade.CpTd0311")
        obj.SetInputValue(0, "1")               # sell
        obj.SetInputValue(1, self._account)
        obj.SetInputValue(2, self._goods_code)
        obj.SetInputValue(3, code)
        obj.SetInputValue(4, qty)
        obj.SetInputValue(8, "03")              # price type: market

        ret = obj.BlockRequest()
        if ret != 0:
            raise RuntimeError(f"Sell BlockRequest failed: ret={ret}")
        status = obj.GetDibStatus()
        msg = obj.GetDibMsg1()
        if status != 0:
            raise RuntimeError(f"Sell order failed: status={status} msg={msg}")
        order_num = obj.GetHeaderValue(8)
        log.info(f"Sell order placed: {code} {qty}@market, order_num={order_num}")
        return {"order_num": order_num}

    def cancel(self, order_num: int, code: str, qty: int) -> dict:
        """Cancel an order. Returns {"status": int, "msg": str}."""
        self._conn.wait_if_limited(1)
        obj = win32com.client.Dispatch("CpTrade.CpTd0314")
        obj.SetInputValue(1, order_num)
        obj.SetInputValue(2, self._account)
        obj.SetInputValue(3, self._goods_code)
        obj.SetInputValue(4, code)
        obj.SetInputValue(5, qty)

        ret = obj.BlockRequest()
        if ret != 0:
            raise RuntimeError(f"Cancel BlockRequest failed: ret={ret}")
        status = obj.GetDibStatus()
        msg = obj.GetDibMsg1()
        log.info(f"Cancel order: {order_num}, status={status}, msg={msg}")
        return {"status": status, "msg": msg}
```

- [ ] **Step 5: Implement account.py**

```python
# src/com/account.py
from __future__ import annotations
import logging
import win32com.client

log = logging.getLogger(__name__)


class CybosAccount:
    def __init__(self):
        self._trade_util = win32com.client.Dispatch("CpTrade.CpTdUtil")

    def init(self) -> None:
        result = self._trade_util.TradeInit(0)
        if result != 0:
            raise RuntimeError(f"TradeInit failed: {result}")
        log.info("Trade initialized")

    @property
    def account_number(self) -> str:
        return self._trade_util.AccountNumber[0]

    @property
    def goods_code(self) -> str:
        acc = self.account_number
        goods_list = self._trade_util.GoodsList(acc, 1)
        return goods_list[0]
```

- [ ] **Step 6: Commit**

```bash
git add src/com/
git commit -m "feat: add CYBOS Plus COM wrappers (connection, code, stock, order, account)"
```

---

### Task 12: News Sources

**Files:**
- Create: `src/news/cybos_news.py`
- Create: `src/news/telegram_news.py`

- [ ] **Step 1: Implement cybos_news.py**

```python
# src/news/cybos_news.py
from __future__ import annotations
import logging
import time
import win32com.client
from src.core.event_bus import EventBus

log = logging.getLogger(__name__)


class CybosNewsHandler:
    callback = None

    def OnReceived(self):
        try:
            code = self._obj.GetHeaderValue(1)
            title = self._obj.GetHeaderValue(5)
            if CybosNewsHandler.callback:
                CybosNewsHandler.callback(code, title)
        except Exception as e:
            log.error(f"CybosNewsHandler error: {e}")


class CybosNewsSource:
    def __init__(self, event_bus: EventBus, code_manager):
        self._event_bus = event_bus
        self._code_manager = code_manager
        self._obj = None

    def start(self) -> None:
        CybosNewsHandler.callback = self._on_news
        self._obj = win32com.client.DispatchWithEvents(
            "Dscbo1.CpSvr8092S", CybosNewsHandler
        )
        self._obj.Subscribe()
        log.info("CYBOS news subscribed")

    def stop(self) -> None:
        if self._obj:
            self._obj.Unsubscribe()
            log.info("CYBOS news unsubscribed")

    def _on_news(self, code: str, title: str) -> None:
        name = self._code_manager.code_to_name(code) or ""
        log.info(f"CYBOS news: [{code}] {name} - {title}")
        self._event_bus.publish("news_feed", {
            "stock_code": code, "stock_name": name,
            "source": "cybos", "text": title,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        if code and name:
            self._event_bus.publish("news_detected", {
                "code": code, "name": name, "source": "cybos",
                "title": title, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
```

- [ ] **Step 2: Implement telegram_news.py**

```python
# src/news/telegram_news.py
from __future__ import annotations
import asyncio
import logging
import threading
import time
from telethon import TelegramClient, events
from src.core.event_bus import EventBus

log = logging.getLogger(__name__)


class TelegramNewsSource:
    def __init__(self, api_id: int, api_hash: str, phone: str,
                 session_name: str, event_bus: EventBus, code_manager):
        self._api_id = api_id
        self._api_hash = api_hash
        self._phone = phone
        self._session_name = session_name
        self._event_bus = event_bus
        self._code_manager = code_manager
        self._channels: list[str] = []
        self._client: TelegramClient | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._auth_code_future: asyncio.Future | None = None

    def set_channels(self, channels: list[str]) -> None:
        self._channels = channels

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("Telegram news listener started")

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._listen())

    async def _listen(self) -> None:
        self._client = TelegramClient(
            self._session_name, self._api_id, self._api_hash
        )
        await self._client.start(phone=self._phone, code_callback=self._code_callback)
        log.info("Telegram client connected")

        @self._client.on(events.NewMessage(chats=self._channels))
        async def handler(event):
            text = event.message.text or ""
            channel_name = getattr(event.chat, "title", "unknown")
            self._on_message(text, channel_name)

        await self._client.run_until_disconnected()

    async def _code_callback(self) -> str:
        log.info("Telegram 2FA code requested")
        self._event_bus.publish("telegram_code_pending", {"pending": True})
        self._auth_code_future = self._loop.create_future()
        code = await self._auth_code_future
        self._event_bus.publish("telegram_code_pending", {"pending": False})
        return code

    def submit_auth_code(self, code: str) -> None:
        if self._auth_code_future and self._loop:
            self._loop.call_soon_threadsafe(self._auth_code_future.set_result, code)

    def _on_message(self, text: str, channel_name: str) -> None:
        log.info(f"Telegram [{channel_name}]: {text[:80]}")
        self._event_bus.publish("news_feed", {
            "stock_code": "", "stock_name": "",
            "source": "telegram", "category": channel_name,
            "text": text, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        # Match stock names from cached list
        matches = self._extract_stocks(text)
        for code, name in matches:
            self._event_bus.publish("news_detected", {
                "code": code, "name": name, "source": "telegram",
                "channel": channel_name, "title": text[:100],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })

    def _extract_stocks(self, text: str) -> list[tuple[str, str]]:
        results = []
        seen = set()
        for name, code in self._code_manager.all_stocks():
            if len(name) >= 2 and name in text and code not in seen:
                results.append((code, name))
                seen.add(code)
        return results
```

- [ ] **Step 3: Commit**

```bash
git add src/news/
git commit -m "feat: add CYBOS and Telegram news sources"
```

---

### Task 13: Telegram Bot Alerts

**Files:**
- Create: `src/telegram/bot.py`

- [ ] **Step 1: Implement bot.py**

```python
# src/telegram/bot.py
from __future__ import annotations
import asyncio
import logging
import threading
from telegram import Bot

log = logging.getLogger(__name__)


class AlertBot:
    def __init__(self, token: str, chat_id: int):
        self._token = token
        self._chat_id = chat_id
        self._bot: Bot | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._bot = Bot(token=self._token)
        self._loop.run_forever()

    def send(self, message: str) -> None:
        if not self._bot or not self._loop:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._bot.send_message(self._chat_id, message), self._loop
            )
        except Exception as e:
            log.error(f"Alert send failed: {e}")

    def on_buy_filled(self, data: dict) -> None:
        msg = (f"[매수 체결] {data.get('name', '')} ({data.get('code', '')})\n"
               f"가격: {data.get('price', 0):,}원 × {data.get('qty', 0)}주")
        self.send(msg)

    def on_sell_filled(self, data: dict) -> None:
        pnl = data.get('pnl_pct', 0) * 100
        sign = "+" if pnl >= 0 else ""
        msg = (f"[매도 체결] {data.get('name', '')} ({data.get('code', '')})\n"
               f"가격: {data.get('price', 0):,}원 × {data.get('qty', 0)}주\n"
               f"수익률: {sign}{pnl:.2f}% ({data.get('reason', '')})")
        self.send(msg)

    def on_trade_done(self, data: dict) -> None:
        pass  # buy/sell_filled covers it
```

- [ ] **Step 2: Commit**

```bash
git add src/telegram/
git commit -m "feat: add Telegram alert bot"
```

---

### Task 14: FastAPI Server & WebSocket

**Files:**
- Create: `src/web/server.py`
- Create: `src/web/websocket.py`

- [ ] **Step 1: Implement websocket.py**

```python
# src/web/websocket.py
from __future__ import annotations
import asyncio
import logging
from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, event_type: str, data: dict) -> None:
        msg = {"type": event_type, "data": data}
        for ws in self._connections[:]:
            try:
                await ws.send_json(msg)
            except Exception:
                self._connections.remove(ws)


class EventBridge:
    """Bridges EventBus (any thread) → WebSocket broadcast (asyncio)."""

    def __init__(self, manager: ConnectionManager):
        self._manager = manager
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def push(self, event_type: str, data: dict) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._manager.broadcast(event_type, data), self._loop
            )
```

- [ ] **Step 2: Implement server.py**

```python
# src/web/server.py
from __future__ import annotations
import asyncio
import logging
import threading
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from src.web.websocket import ConnectionManager, EventBridge
from src.web.routes import status, trades, stats, settings, news, logs

log = logging.getLogger(__name__)

ws_manager = ConnectionManager()
event_bridge = EventBridge(ws_manager)

# Global references set by start_server
_app_context: dict = {}


def get_context() -> dict:
    return _app_context


@asynccontextmanager
async def lifespan(app: FastAPI):
    event_bridge.set_loop(asyncio.get_event_loop())
    yield

app = FastAPI(lifespan=lifespan)

# Register routes
app.include_router(status.router, prefix="/api")
app.include_router(trades.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(logs.router, prefix="/api")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except Exception:
        ws_manager.disconnect(ws)


def start_server(context: dict, host: str = "0.0.0.0", port: int = 8000) -> threading.Thread:
    """Start uvicorn in a daemon thread. context dict is shared with routes."""
    _app_context.update(context)

    # Subscribe event_bus events to WebSocket bridge
    event_bus = context.get("event_bus")
    if event_bus:
        for evt in ("cybos_status", "engine_status", "news_feed", "news_detected",
                     "worker_state", "buy_filled", "sell_filled", "trade_done"):
            event_bus.subscribe(evt, lambda data, t=evt: event_bridge.push(t, data))

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    log.info(f"Web server started on {host}:{port}")
    return thread
```

- [ ] **Step 3: Commit**

```bash
git add src/web/server.py src/web/websocket.py
git commit -m "feat: add FastAPI server with WebSocket broadcast"
```

---

### Task 15: API Routes

**Files:**
- Create: `src/web/routes/status.py`
- Create: `src/web/routes/trades.py`
- Create: `src/web/routes/stats.py`
- Create: `src/web/routes/settings.py`
- Create: `src/web/routes/news.py`
- Create: `src/web/routes/logs.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Implement status.py**

```python
# src/web/routes/status.py
from __future__ import annotations
import subprocess
from fastapi import APIRouter
from src.web.server import get_context

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
```

- [ ] **Step 2: Implement trades.py**

```python
# src/web/routes/trades.py
from __future__ import annotations
from fastapi import APIRouter, Query
from src.web.server import get_context

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
```

- [ ] **Step 3: Implement stats.py**

```python
# src/web/routes/stats.py
from __future__ import annotations
from fastapi import APIRouter, Query
from src.web.server import get_context

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
```

- [ ] **Step 4: Implement settings.py**

```python
# src/web/routes/settings.py
from __future__ import annotations
import json
from fastapi import APIRouter
from src.web.server import get_context

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
    # Reload engine params if running
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
```

- [ ] **Step 5: Implement news.py**

```python
# src/web/routes/news.py
from __future__ import annotations
import time
from fastapi import APIRouter
from src.web.server import get_context

router = APIRouter()

_news_buffer: list[dict] = []
_MAX_NEWS = 200


@router.get("/news-feed")
async def get_news_feed():
    return _news_buffer[-100:]


@router.post("/test/news")
async def test_news(body: dict):
    ctx = get_context()
    event_bus = ctx.get("event_bus")
    if event_bus:
        news_data = {
            "code": body.get("stock_code", ""),
            "name": body.get("stock_name", ""),
            "source": "test",
            "title": body.get("text", "Test news"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        event_bus.publish("news_detected", news_data)
        event_bus.publish("news_feed", {
            "stock_code": news_data["code"], "stock_name": news_data["name"],
            "source": "test", "text": news_data["title"],
            "timestamp": news_data["timestamp"],
        })
    return {"status": "ok"}


def register_news_buffer(event_bus) -> None:
    """Call at startup to capture news events for the buffer."""
    def on_news_feed(data):
        _news_buffer.append(data)
        while len(_news_buffer) > _MAX_NEWS:
            _news_buffer.pop(0)
    event_bus.subscribe("news_feed", on_news_feed)
```

- [ ] **Step 6: Implement logs.py**

```python
# src/web/routes/logs.py
from __future__ import annotations
import os
from fastapi import APIRouter, Query
from src.web.server import get_context
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
            # Extract date from filename
            if f == "systrader.log":
                import datetime
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
    import datetime
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
```

- [ ] **Step 7: Write API integration test**

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from src.database import Database
from src.core.event_bus import EventBus
from src.core.command_queue import CommandQueue
from src.web.server import app, _app_context


@pytest.fixture
def client(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.ensure_schema()
    _app_context.clear()
    _app_context.update({
        "db": db,
        "event_bus": EventBus(),
        "command_queue": CommandQueue(),
        "connection": None,
        "account": None,
        "engine": None,
        "telegram_news": None,
        "settings_path": str(tmp_path / "settings.json"),
        "log_dir": str(tmp_path / "logs"),
    })
    import json, os
    with open(str(tmp_path / "settings.json"), "w") as f:
        json.dump({"Web": {"Port": 8000}}, f)
    os.makedirs(str(tmp_path / "logs"), exist_ok=True)
    return TestClient(app)


def test_get_trades_empty(client):
    resp = client.get("/api/trades")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_params_empty(client):
    resp = client.get("/api/settings/params")
    assert resp.status_code == 200
    assert resp.json() == []


def test_update_and_get_param(client):
    client.put("/api/settings/params/max_holdings", json={"value": "5"})
    resp = client.get("/api/settings/params")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["key"] == "max_holdings"
    assert data[0]["value"] == "5"


def test_channels_crud(client):
    client.post("/api/settings/channels", json={
        "channel_url": "https://t.me/test", "channel_name": "Test"
    })
    resp = client.get("/api/settings/channels")
    assert len(resp.json()) == 1

    client.put("/api/settings/channels/1/toggle")
    resp = client.get("/api/settings/channels")
    assert resp.json()[0]["enabled"] == 0

    client.delete("/api/settings/channels/1")
    resp = client.get("/api/settings/channels")
    assert resp.json() == []


def test_get_status_without_cybos(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cybos_connected"] is False


def test_news_feed(client):
    resp = client.get("/api/news-feed")
    assert resp.status_code == 200


def test_logs_live(client):
    resp = client.get("/api/logs/live?after=0")
    assert resp.status_code == 200
    assert "logs" in resp.json()
```

- [ ] **Step 8: Run tests**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/web/routes/ tests/test_api.py
git commit -m "feat: add all REST API routes with tests"
```

---

### Task 16: Main Entry Point

**Files:**
- Create: `main.py`

- [ ] **Step 1: Implement main.py**

```python
# main.py
"""
SysTrader — News Scalping Automated Trading System
Entry point: COM STA main loop + uvicorn thread + Telegram threads

Requires: 32-bit Python, CYBOS Plus connected, admin privileges
"""
from __future__ import annotations
import logging
import os
import sys
import time

log = logging.getLogger("systrader")


def main():
    import pythoncom
    import win32event

    from src.config import load_settings
    from src.database import Database
    from src.core.event_bus import EventBus
    from src.core.command_queue import CommandQueue
    from src.core.log import setup_logging
    from src.com.connection import CybosConnection
    from src.com.code import CodeManager
    from src.com.stock import StockMst, StockCurManager
    from src.com.order import CybosOrder
    from src.com.account import CybosAccount
    from src.engine.trading_engine import TradingEngine
    from src.news.cybos_news import CybosNewsSource
    from src.news.telegram_news import TelegramNewsSource
    from src.telegram.bot import AlertBot
    from src.web.server import start_server
    from src.web.routes.news import register_news_buffer

    # 1. Load settings
    settings_path = "appsettings.json"
    if not os.path.exists(settings_path):
        log.error(f"{settings_path} not found. Copy appsettings.example.json and configure.")
        sys.exit(1)
    settings = load_settings(settings_path)

    # 2. Setup logging
    log_buffer = setup_logging(settings.logging.dir, settings.logging.log_level)
    log.info("SysTrader starting...")

    # 3. Initialize DB
    db = Database(settings.db.path)
    db.ensure_schema()
    log.info(f"Database ready: {settings.db.path}")

    # 4. Core infrastructure
    event_bus = EventBus()
    command_queue = CommandQueue()

    # 5. COM initialization (main thread STA)
    pythoncom.CoInitialize()
    log.info("COM initialized (STA)")

    connection = CybosConnection()
    if not connection.is_connected:
        log.warning("CYBOS Plus not connected. Some features disabled.")

    code_manager = CodeManager()
    if connection.is_connected:
        code_manager.load_stock_list()

    account = None
    order = None
    if connection.is_connected:
        try:
            account = CybosAccount()
            account.init()
            order = CybosOrder(connection, account.account_number, account.goods_code)
            log.info(f"Account: {account.account_number}")
        except Exception as e:
            log.error(f"Account init failed: {e}")

    # 6. Stock tick manager
    stock_mst = StockMst(connection)

    def get_stock_info(code):
        return stock_mst.request(code)

    stock_cur_manager = StockCurManager(on_tick=lambda code, data: engine.on_tick(code, data))

    # 7. Trading engine
    def handle_order(order_type, code, qty, price):
        if order_type == "BUY":
            order.buy_limit(code, qty, price)
        elif order_type == "SELL_MARKET":
            order.sell_market(code, qty)

    engine = TradingEngine(
        db=db, event_bus=event_bus,
        order_func=handle_order,
        stock_info_func=get_stock_info,
        subscribe_tick_func=stock_cur_manager.subscribe,
        unsubscribe_tick_func=stock_cur_manager.unsubscribe,
    )

    # Wire news → engine
    event_bus.subscribe("news_detected", engine.on_news)

    # 8. CYBOS news source
    cybos_news = None
    if connection.is_connected:
        try:
            cybos_news = CybosNewsSource(event_bus, code_manager)
            cybos_news.start()
        except Exception as e:
            log.error(f"CYBOS news subscription failed: {e}")

    # 9. Telegram news listener
    telegram_news = None
    if settings.telegram_listener.api_id:
        telegram_news = TelegramNewsSource(
            api_id=settings.telegram_listener.api_id,
            api_hash=settings.telegram_listener.api_hash,
            phone=settings.telegram_listener.phone,
            session_name=settings.telegram_listener.session_name,
            event_bus=event_bus, code_manager=code_manager,
        )
        channels = db.channels.list()
        telegram_news.set_channels([c["channel_url"] for c in channels if c["enabled"]])
        telegram_news.start()

    # 10. Telegram alert bot
    alert_bot = None
    if settings.telegram_bot.token:
        alert_bot = AlertBot(settings.telegram_bot.token, settings.telegram_bot.chat_id)
        alert_bot.start()
        event_bus.subscribe("buy_filled", alert_bot.on_buy_filled)
        event_bus.subscribe("sell_filled", alert_bot.on_sell_filled)

    # 11. News buffer for API
    register_news_buffer(event_bus)

    # 12. Start web server
    context = {
        "db": db, "event_bus": event_bus, "command_queue": command_queue,
        "connection": connection, "account": account, "engine": engine,
        "telegram_news": telegram_news, "settings": settings,
        "settings_path": settings_path, "log_dir": settings.logging.dir,
    }
    start_server(context, settings.web.host, settings.web.port)

    # 13. Command handler
    def handle_command(cmd, params):
        if cmd == "engine_start":
            engine.start()
            return {"status": "ok"}
        elif cmd == "engine_stop":
            engine.stop()
            return {"status": "ok"}
        elif cmd == "launch_cybos":
            import subprocess
            subprocess.Popen(settings.cybos.exe_path)
            return {"status": "ok"}
        return {"status": "unknown_command"}

    command_queue.register_handler(handle_command)

    # 14. Main loop — COM message pump
    stop_event = win32event.CreateEvent(None, 0, 0, None)
    cmd_event = command_queue.get_event()
    log.info("Entering main loop. Web UI: http://localhost:%d", settings.web.port)

    try:
        while True:
            handles = [stop_event]
            # Include command event if it's a valid handle
            rc = win32event.MsgWaitForMultipleObjects(
                handles, 0, 50, win32event.QS_ALLEVENTS
            )
            if rc == win32event.WAIT_OBJECT_0:
                break
            elif rc == win32event.WAIT_OBJECT_0 + len(handles):
                pythoncom.PumpWaitingMessages()

            # Always process command queue
            if command_queue.has_pending():
                command_queue.process()

            # Periodic: check connection
            if connection.is_connected:
                pass  # Could add periodic health check here

    except KeyboardInterrupt:
        log.info("Shutdown requested")
    finally:
        log.info("Shutting down...")
        engine.stop()
        stock_cur_manager.unsubscribe_all()
        if cybos_news:
            cybos_news.stop()
        db.close()
        log.info("SysTrader stopped")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add main.py
git commit -m "feat: add main entry point with COM loop and thread orchestration"
```

---

### Task 17: Frontend Setup

**Files:**
- Copy: `autotrader/web/` → `systrader/web/`

- [ ] **Step 1: Copy the web directory from autotrader**

```bash
cp -r /c/Users/wooo1/projects/autotrader/web /c/Users/wooo1/projects/systrader/web
```

- [ ] **Step 2: Update vite.config.ts proxy (if port differs)**

The vite config already proxies to `localhost:8000` which matches our FastAPI server config. No changes needed unless the port changes.

- [ ] **Step 3: Verify the frontend API client paths match**

Check that `web/src/api/client.ts` paths match the routes defined in Task 15. The autotrader client uses these paths which all match:
- `/status` → `GET /api/status`
- `/engine/start` → `POST /api/engine/start`
- `/engine/stop` → `POST /api/engine/stop`
- `/trades` → `GET /api/trades`
- `/news-feed` → `GET /api/news-feed`
- `/logs/live` → `GET /api/logs/live`

One mismatch to fix: autotrader uses `/cybos/launch` but we defined `/engine/launch-cybos`.

- [ ] **Step 4: Fix the launch-cybos path in client.ts**

In `web/src/api/client.ts`, change:
```typescript
// Old:
export function launchCybos(): Promise<{ status: string }> {
  return postJson("/cybos/launch");
}

// New:
export function launchCybos(): Promise<{ status: string }> {
  return postJson("/engine/launch-cybos");
}
```

- [ ] **Step 5: Install frontend dependencies and verify build**

```bash
cd /c/Users/wooo1/projects/systrader/web && npm install && npm run build
```

Expected: Build succeeds, output in `web/dist/`

- [ ] **Step 6: Mount static files in FastAPI**

Add to `src/web/server.py` after route registration:

```python
import os
_static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "web", "dist")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
```

- [ ] **Step 7: Commit**

```bash
cd /c/Users/wooo1/projects/systrader
git add web/ src/web/server.py
git commit -m "feat: add React frontend (copied from autotrader, updated API paths)"
```

---

### Task 18: Final Integration & README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README.md with setup instructions**

```markdown
# SysTrader

News scalping automated trading system using CYBOS Plus COM API.

## Requirements

- Windows 10/11
- Python 3.x **32-bit** (CYBOS COM is 32-bit only)
- CYBOS Plus installed and logged in
- Node.js 18+ (for frontend build)

## Setup

```bash
# 1. Create virtual environment (32-bit Python)
python -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
copy appsettings.example.json appsettings.json
# Edit appsettings.json with your Telegram credentials

# 4. Build frontend
cd web
npm install
npm run build
cd ..

# 5. Initialize database
python -c "from src.database import Database; db = Database('data/systrader.db'); db.ensure_schema()"

# 6. Run
python main.py
```

## Usage

- Web UI: http://localhost:8000
- Start engine via Dashboard or `POST /api/engine/start`
- Configure parameters via Settings page

## PoC

Before first run, verify CYBOS news events work:

```bash
python poc/test_news_event.py
```
```

- [ ] **Step 2: Run full test suite**

```bash
cd /c/Users/wooo1/projects/systrader
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup instructions"
```

- [ ] **Step 4: Push to remote**

```bash
git remote add origin https://github.com/wooo1932/systrader.git
git branch -M main
git push -u origin main
```
