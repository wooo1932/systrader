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
