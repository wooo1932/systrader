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
        if time.time() - self._screen_start > self.params["entry_timeout_sec"]:
            self._set_state(WorkerState.CANCELLED)
            return

        if self._last_price > 0 and price > self._last_price:
            self._consecutive_up += 1
        elif self._last_price > 0 and price < self._last_price:
            self._consecutive_up = 0

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

        vi_detected = (time.time() - self._last_tick_time) > self.params["vi_detect_sec"]
        if vi_detected:
            self.bpi.reset()
            self._hold_paused += time.time() - self._last_tick_time
            pnl_pct = (price - self.buy_price) / self.buy_price
            if pnl_pct <= self.params["stoploss_pct"]:
                self._place_sell_order(price, "stoploss")
            return

        is_buy = tick["bid_or_ask"] == "buy"
        self.bpi.add(is_buy)

        pnl_pct = (price - self.buy_price) / self.buy_price
        drop_pct = (price - self.highest_price) / self.highest_price if self.highest_price > 0 else 0
        hold_time = time.time() - self._hold_start - self._hold_paused

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
