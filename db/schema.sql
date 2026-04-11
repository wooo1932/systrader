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
