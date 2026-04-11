# SysTrader — News Scalping Automated Trading System

## Overview

A Python-based automated stock trading system that monitors real-time news from CYBOS Plus and Telegram, filters stocks by configurable criteria, and executes buy/sell orders through the CYBOS Plus COM API. The web frontend is reused from the existing autotrader project (React 19 + Vite + TypeScript).

**Tech Stack:**
- Backend: Python 3.x (32-bit), FastAPI, uvicorn, SQLite
- COM: CYBOS Plus (win32com, pythoncom)
- Telegram: Telethon (listener), python-telegram-bot (alerts)
- Frontend: React 19, TypeScript, Vite, React Router 7, Recharts (reused from autotrader)

---

## 1. Project Structure

```
systrader/
├── CLAUDE.md
├── README.md
├── .gitignore
├── requirements.txt
├── appsettings.json
├── main.py                     # Entry point: COM STA main loop + uvicorn thread
├── db/
│   └── schema.sql              # SQLite DDL (same as autotrader)
├── data/                       # Runtime data (DB file)
├── logs/                       # Log files
├── docs/
│   └── superpowers/specs/
├── web/                        # React+Vite frontend (copied from autotrader)
├── poc/
│   └── test_news_event.py      # COM event verification PoC
└── src/
    ├── __init__.py
    ├── config.py               # appsettings.json loader, Pydantic models
    ├── database.py             # SQLite connection, repositories
    ├── models.py               # Trade, Tick, Parameter Pydantic models
    ├── com/
    │   ├── __init__.py
    │   ├── connection.py       # CpCybos connection status, API limit check
    │   ├── news.py             # CpSvr8092S news events
    │   ├── stock.py            # StockMst, StockCur, MarketEye
    │   ├── order.py            # CpTd0311 buy, CpTd0314 cancel
    │   ├── code.py             # CpStockCode, CpCodeMgr
    │   └── account.py          # CpTdUtil account
    ├── engine/
    │   ├── __init__.py
    │   ├── trading_engine.py   # Engine start/stop, Worker management
    │   ├── worker.py           # StockWorker state machine
    │   ├── screener.py         # Stock filtering (market cap, change %)
    │   ├── bpi.py              # BPI calculator
    │   └── tick_unit.py        # Price tick unit calculation
    ├── news/
    │   ├── __init__.py
    │   ├── cybos_news.py       # CYBOS news event handler
    │   └── telegram_news.py    # Telethon-based Telegram monitoring
    ├── telegram/
    │   └── bot.py              # Trade alert bot
    ├── web/
    │   ├── __init__.py
    │   ├── server.py           # uvicorn thread, FastAPI app
    │   ├── routes/
    │   │   ├── status.py       # GET /api/status, POST /api/engine/*
    │   │   ├── trades.py       # GET /api/trades, /api/trades/{id}/*
    │   │   ├── stats.py        # GET /api/stats/*
    │   │   ├── settings.py     # GET/PUT /api/settings/*
    │   │   ├── news.py         # GET /api/news-feed, POST /api/test/news
    │   │   └── logs.py         # GET /api/logs/*
    │   └── websocket.py        # WebSocket broadcast
    └── core/
        ├── __init__.py
        ├── event_bus.py        # Thread-safe event delivery (Queue-based)
        └── log.py              # Logging setup + LogBuffer
```

---

## 2. Thread Architecture & Communication

```
┌──────────────────────────────────────────────────┐
│                Main Thread (STA)                  │
│                                                    │
│  pythoncom.CoInitialize()                         │
│  COM objects (news, tick, order, connection)       │
│                                                    │
│  MsgWaitForMultipleObjects loop:                  │
│    - PumpWaitingMessages() → COM event dispatch   │
│    - process_command_queue() → order execution    │
│                                                    │
│  COM event callbacks:                             │
│    news → event_bus.publish("news_detected")      │
│    tick → event_bus.publish("tick")               │
│    fill → event_bus.publish("fill")               │
│                                                    │
│  TradingEngine runs here (Worker state machine)   │
└──────────┬──────────────────────┬─────────────────┘
           │ event_bus (Queue)    │ command_queue
           ▼                     ▲
┌──────────────────────┐  ┌──────────────────────────┐
│  FastAPI Thread       │  │  Telethon Thread          │
│  uvicorn (REST+WS)    │  │  asyncio event loop       │
│  events → WS broadcast│  │  channel messages →       │
│  orders → cmd queue   │  │    event_bus.publish      │
└──────────────────────┘  └──────────────────────────┘
                           ┌──────────────────────────┐
                           │  Telegram Bot Thread      │
                           │  python-telegram-bot      │
                           │  event_bus subscribe →    │
                           │    send trade alerts      │
                           └──────────────────────────┘
```

### EventBus

Thread-safe, multi-consumer event delivery:

```python
class EventBus:
    def publish(event_type: str, data: dict)     # callable from any thread
    def subscribe(event_type: str, callback)     # callback runs in caller's thread
    async def wait_event(event_type: str) -> dict  # asyncio.Queue for FastAPI
```

### CommandQueue

FastAPI → main thread (COM operations):

```python
class CommandQueue:
    def put(command: str, params: dict, future: Future)
    def process()  # called from main thread, sets result on future
```

Usage: FastAPI puts a command, awaits the future. Main thread picks it up, executes COM call, sets result.

### Rules

- **COM object calls MUST happen on main thread only** — via command_queue
- **Events flow one-way** through event_bus — COM → engine/web/bot
- **TradingEngine runs on main thread** — COM callbacks drive Worker state transitions
- **DB reads** — allowed from any thread (SQLite WAL mode)
- **DB writes** — from main thread (engine) only

---

## 3. Trading Engine & Worker State Machine

### TradingEngine

```python
class TradingEngine:
    workers: dict[str, StockWorker]  # stock_code → worker

    def on_news(news_data):
        # extract stock codes → screener filter → create Worker
    def on_tick(code, tick_data):
        # forward to worker
    def on_fill(order_data):
        # forward to worker
```

### Worker State Machine

```
Screening ──(filter pass)──→ Buying ──(filled)──→ Holding ──(sell signal)──→ Selling ──(filled)──→ Done
    │                          │                     │                         │
    └──(filter fail)──→ Cancelled  (timeout)──→ Cancelled                   (fail)──→ Done
```

### Screening Phase

- Subscribe to StockCur real-time ticks
- Check entry conditions on each tick:
  - max consecutive up ticks >= `entry_up_ticks`
  - buy tick ratio >= `entry_buy_ratio`
- Timeout: `entry_timeout_sec`

### Buying Phase

- Limit buy order: `current_price + tick_unit(price) * buy_tick_offset`
- Quantity: `bet_amount // buy_price`
- Fill timeout: `fill_timeout_sec` → cancel order → Cancelled

### Holding Phase — Exit Signals (4 types)

| Signal | Condition | Parameter |
|--------|-----------|-----------|
| Stoploss | pnl_pct <= threshold | `stoploss_pct` |
| Maxdrop | (current - highest) / highest <= threshold | `maxdrop_pct` |
| BPI reversal | ShortBPI <= LongBPI AND ShortBPI < threshold | `bpi_sell_threshold` |
| Timeout | hold time >= max | `max_hold_sec` |

### BPI (Buy Pressure Index)

- Short window (default 10 ticks): buy tick ratio in recent ticks
- Long window (default 30 ticks): buy tick ratio in longer history
- Sell signal when short-term buying pressure drops below long-term

### VI Detection

- No ticks for `vi_detect_sec` seconds → BPI reset, only stoploss checked, hold timer paused

### Tick Unit Table

| Price Range | Unit |
|-------------|------|
| < 2,000 | 1 |
| < 5,000 | 5 |
| < 10,000 | 10 |
| < 50,000 | 50 |
| < 200,000 | 100 |
| < 500,000 | 500 |
| >= 500,000 | 1,000 |

---

## 4. COM Wrapper Layer

Based on official Daishin Securities Python examples. Reference: https://money2.daishin.com/e5/mboard/ptype_basic/plusPDS/DW_Basic_List.aspx?boardseq=299&m=9508&p=8831&v=8638

### Main Loop (MessagePump pattern)

```python
def main_loop():
    pythoncom.CoInitialize()
    # initialize COM objects...

    while running:
        rc = win32event.MsgWaitForMultipleObjects(
            [stop_event, command_event],
            0, 10, win32event.QS_ALLEVENTS
        )
        if rc == win32event.WAIT_OBJECT_0:
            break  # stop signal
        elif rc == win32event.WAIT_OBJECT_0 + 1:
            process_command_queue()
        elif rc == win32event.WAIT_OBJECT_0 + 2:
            pythoncom.PumpWaitingMessages()
        elif rc == win32event.WAIT_TIMEOUT:
            pythoncom.PumpWaitingMessages()
```

### Key COM Objects

| ProgID | Purpose | Pattern |
|--------|---------|---------|
| CpUtil.CpCybos | Connection, API limits | Dispatch, property access |
| CpUtil.CpStockCode | Code/name lookup | Dispatch |
| CpUtil.CpCodeMgr | Market type, stock list | Dispatch |
| CpTrade.CpTdUtil | Trade init, account | Dispatch, TradeInit(0) |
| Dscbo1.CpSvr8092S | Real-time news (event) | DispatchWithEvents |
| Dscbo1.StockMst | Stock master (price, cap) | BlockRequest |
| Dscbo1.StockCur | Real-time tick (event) | DispatchWithEvents |
| CpTrade.CpTd0311 | Buy/sell order | BlockRequest + GetDibStatus |
| CpTrade.CpTd0314 | Order cancel | BlockRequest + GetDibStatus |
| CpSysDib.MarketEye | Batch quote | BlockRequest |

### Error Handling for Orders

Following official example pattern:
1. `BlockRequest()` return value must be 0
2. `GetDibStatus()` must be 0
3. `GetDibMsg1()` for error description
4. Return value 4 = API call limit exceeded

### API Rate Limiting

- Non-trade: ~15 calls / 15 sec → `CpCybos.GetLimitRemainCount(0)`
- Trade: ~5 calls / 15 sec → `CpCybos.GetLimitRemainCount(1)`
- Wait and retry when limit reached

---

## 5. News Sources

### CYBOS News (CpSvr8092S)

- Event-based via `DispatchWithEvents`
- Provides both stock code and stock name
- Publishes to event_bus as `news_detected`
- **Must verify in PoC first** — may not fire events in Python

### Telegram News (Telethon)

- Runs in separate thread with own asyncio loop
- Monitors configured channels for new messages
- Extracts stock names from message text by matching against cached stock name list
- Stock name → code lookup via `CpStockCode` (cached at startup from `CpCodeMgr`)
- Publishes to event_bus as `news_detected`

### Stock Name Matching

Telegram news contains stock names, not codes. At startup, `CpCodeMgr` provides the full stock list which is cached in memory. When a Telegram message arrives, stock names are matched against this cache to resolve codes.

### Telegram Bot Alerts

- Separate thread, python-telegram-bot library
- Subscribes to event_bus for: `buy_filled`, `sell_filled`, `trade_done`
- Sends formatted alert messages to configured chat

---

## 6. Web Server & API Layer

### FastAPI Server

- Runs in daemon thread via `uvicorn.Server`
- Serves REST API at `/api/*` and WebSocket at `/ws`
- Serves React build from `web/dist/` as static files

### WebSocket

- Endpoint: `/ws`
- JSON messages: `{"type": "event_type", "data": {...}}`
- Events: `cybos_status`, `engine_status`, `news_feed`, `news_detected`, `worker_state`, `buy_filled`, `sell_filled`, `trade_done`
- EventBridge: COM thread events → `asyncio.run_coroutine_threadsafe` → WebSocket broadcast

### REST API Endpoints

Identical paths to autotrader for frontend compatibility:

**Status & Control:**
- `GET /api/status`
- `POST /api/engine/start|stop|launch-cybos`
- `POST /api/telegram/auth-code`

**Trades:**
- `GET /api/trades?status=&date=&limit=100&news_source=`
- `GET /api/trades/{id}`
- `GET /api/trades/{id}/ticks`

**Statistics:**
- `GET /api/stats/summary?date_from=&date_to=&source=`
- `GET /api/stats/daily?days=365`

**Settings:**
- `GET /api/settings/params`
- `PUT /api/settings/params/{key}`
- `GET /api/settings/params/history`
- `GET /api/settings/config`
- `PUT /api/settings/config`
- `GET /api/settings/channels`
- `POST /api/settings/channels`
- `DELETE /api/settings/channels/{id}`
- `PUT /api/settings/channels/{id}/toggle`

**News & Logs:**
- `GET /api/news-feed`
- `POST /api/test/news`
- `GET /api/logs/live?after=0`
- `GET /api/logs/dates`
- `GET /api/logs/{date}`

### DB Access Rules

- **Reads** (trades, stats, logs, settings queries): FastAPI thread, direct DB access
- **Writes** (trade create/update, tick save): Main thread (engine) only
- SQLite `check_same_thread=False` + WAL mode for concurrent read/write

---

## 7. Database Schema

Identical to autotrader. Key tables:

- **trades** — Core trade records (code, name, buy/sell price/qty/time, pnl, status, etc.)
- **trade_executions** — Buy/sell order executions (trade_id, side, price, quantity)
- **ticks** — Price tick data per trade (trade_id, price, volume, bid_or_ask, timestamp)
- **parameters** — Strategy parameters (key-value, updated_at)
- **parameter_history** — Audit trail (key, old_value, new_value)
- **news_channels** — Telegram channels (url, name, enabled)
- **daily_stats** — Pre-calculated daily statistics

---

## 8. Configuration

### appsettings.json

App-level config: CYBOS path, Telegram credentials, web server host/port, DB path, logging.

Loaded via Pydantic models at startup. Modifiable at runtime via `PUT /api/settings/config`.

### Strategy Parameters (DB)

Runtime-modifiable via `PUT /api/settings/params/{key}`. All parameters with defaults:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| max_holdings | int | 3 | Max concurrent positions |
| min_market_cap | int | 50B | Min market cap (KRW) |
| max_market_cap | int | 1T | Max market cap (KRW) |
| min_change_pct | float | 5.0 | Min price change % |
| max_change_pct | float | 28.0 | Max price change % |
| entry_up_ticks | int | 3 | Consecutive up ticks for entry |
| entry_timeout_sec | int | 60 | Entry wait timeout |
| entry_buy_ratio | float | 0.6 | Min buy tick ratio for entry |
| buy_tick_offset | int | 1 | Buy price offset in tick units |
| bet_amount | int | 1,000,000 | Amount per trade (KRW) |
| fill_timeout_sec | int | 10 | Order fill timeout |
| bpi_short_window | int | 10 | BPI short window size |
| bpi_long_window | int | 30 | BPI long window size |
| bpi_sell_threshold | float | 0.4 | BPI sell signal threshold |
| stoploss_pct | float | -0.03 | Stop loss ratio |
| maxdrop_pct | float | -0.02 | Max drop from high ratio |
| max_hold_sec | int | 300 | Max hold time (seconds) |
| vi_detect_sec | float | 3.0 | VI detection time (seconds) |

---

## 9. Logging

- **File**: `logs/YYYY-MM-DD.log`, daily rotation via `TimedRotatingFileHandler`
- **Console**: stdout
- **LogBuffer**: In-memory deque (maxlen=1000) for `/api/logs/live` polling
- **Levels**: configurable in appsettings.json

---

## 10. PoC Plan

**Before main development**, verify CpSvr8092S news events work in Python:

1. Create `poc/test_news_event.py`
2. Test `DispatchWithEvents("Dscbo1.CpSvr8092S", Handler)` with message pump
3. Verify `OnReceived` callback fires and `GetHeaderValue` returns data

**Fallback if PoC fails:**
1. Try `WithEvents` pattern instead of `DispatchWithEvents`
2. Try polling-based approach (periodic BlockRequest)
3. Last resort: operate with Telegram news only

---

## 11. Error Handling

| Scenario | Handling |
|----------|----------|
| CYBOS disconnected | Periodic `IsConnect` check, pause engine, wait for reconnect |
| API rate limit exceeded | `GetLimitRemainCount` check, sleep and retry |
| Order BlockRequest failure | Check `GetDibStatus`, log + alert, Worker → Cancelled |
| Fill timeout | Cancel order after `fill_timeout_sec`, Worker → Cancelled |
| Telegram disconnected | Telethon auto-reconnect, log + alert on failure |
| DB write failure | Log + alert, trading continues (memory data priority) |
| Worker exception | Only affected Worker → Cancelled, others unaffected |

---

## 12. Startup Flow

```
main.py:
  1. Load appsettings.json → AppSettings
  2. Initialize DB (ensure schema)
  3. Setup logging (file + console + LogBuffer)
  4. Create EventBus, CommandQueue
  5. Start FastAPI server (daemon thread)
  6. Start Telegram news listener (daemon thread)
  7. Start Telegram alert bot (daemon thread)
  8. pythoncom.CoInitialize() on main thread
  9. Initialize COM objects (CybosConnection, CodeManager)
  10. Enter main loop (MsgWaitForMultipleObjects)
      - Engine starts on /api/engine/start command
```
