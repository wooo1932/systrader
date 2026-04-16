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
        elapsed = time.time() - self._screen_start
        if elapsed > self.params["entry_timeout_sec"]:
            log.info(f"[{self.stock_code}] Screening timeout after {elapsed:.1f}s, "
                     f"ticks={len(self._ticks)}, consecutive_up={self._consecutive_up}")
            self._set_state(WorkerState.CANCELLED)
            return

        if self._last_price > 0 and price > self._last_price:
            self._consecutive_up += 1
        elif self._last_price > 0 and price < self._last_price:
            self._consecutive_up = 0

        buy_count = sum(1 for t in self._ticks if t["bid_or_ask"] == "buy")
        buy_ratio = buy_count / len(self._ticks) if self._ticks else 0

        if len(self._ticks) % 20 == 0:
            log.info(f"[{self.stock_code}] Screening: price={price}, ticks={len(self._ticks)}, "
                     f"up={self._consecutive_up}/{self.params['entry_up_ticks']}, "
                     f"buy_ratio={buy_ratio:.2f}/{self.params['entry_buy_ratio']}")

        if (self._consecutive_up >= self.params["entry_up_ticks"]
                and buy_ratio >= self.params["entry_buy_ratio"]):
            log.info(f"[{self.stock_code}] Entry signal! up={self._consecutive_up}, "
                     f"buy_ratio={buy_ratio:.2f}, price={price}")
            self._place_buy_order(price)

    def _place_buy_order(self, current_price: float) -> None:
        tick_unit = get_tick_unit(current_price)
        order_price = int(current_price + tick_unit * self.params["buy_tick_offset"])
        qty = self.params["bet_amount"] // order_price
        if qty <= 0:
            log.warning(f"[{self.stock_code}] Buy cancelled: qty=0 (bet={self.params['bet_amount']}, price={order_price})")
            self._set_state(WorkerState.CANCELLED)
            return
        self.buy_order_price = order_price
        log.info(f"[{self.stock_code}] Placing buy order: {qty}@{order_price} "
                 f"(current={current_price}, tick_unit={tick_unit}, bet={self.params['bet_amount']})")
        self._set_state(WorkerState.BUYING)
        self._on_order("BUY", self.stock_code, qty, order_price)

    def _handle_holding(self, tick: dict, price: float) -> None:
        prev_highest = self.highest_price
        self.highest_price = max(self.highest_price, price)

        vi_detected = (time.time() - self._last_tick_time) > self.params["vi_detect_sec"]
        if vi_detected:
            pause_dur = time.time() - self._last_tick_time
            self.bpi.reset()
            self._hold_paused += pause_dur
            pnl_pct = (price - self.buy_price) / self.buy_price
            log.info(f"[{self.stock_code}] VI detected: pause={pause_dur:.1f}s, "
                     f"price={price}, pnl={pnl_pct:+.2%}")
            if pnl_pct <= self.params["stoploss_pct"]:
                self._place_sell_order(price, "stoploss")
            return

        is_buy = tick["bid_or_ask"] == "buy"
        self.bpi.add(is_buy)

        pnl_pct = (price - self.buy_price) / self.buy_price
        drop_pct = (price - self.highest_price) / self.highest_price if self.highest_price > 0 else 0
        hold_time = time.time() - self._hold_start - self._hold_paused
        bpi_short = self.bpi.short if self.bpi else 0

        if len(self._ticks) % 50 == 0:
            log.info(f"[{self.stock_code}] Holding: price={price}, pnl={pnl_pct:+.2%}, "
                     f"high={self.highest_price}, drop={drop_pct:+.2%}, "
                     f"bpi={bpi_short:.2f}, hold={hold_time:.0f}s")

        if price > prev_highest:
            log.info(f"[{self.stock_code}] New high: {price} (pnl={pnl_pct:+.2%})")

        if pnl_pct <= self.params["stoploss_pct"]:
            log.info(f"[{self.stock_code}] Stoploss triggered: pnl={pnl_pct:+.2%}")
            self._place_sell_order(price, "stoploss")
        elif drop_pct <= self.params["maxdrop_pct"]:
            log.info(f"[{self.stock_code}] Maxdrop triggered: drop={drop_pct:+.2%} from high={self.highest_price}")
            self._place_sell_order(price, "maxdrop")
        elif self.bpi.is_sell_signal(self.params["bpi_sell_threshold"]):
            log.info(f"[{self.stock_code}] BPI sell signal: bpi_short={self.bpi.short:.2f}, bpi_long={self.bpi.long:.2f}")
            self._place_sell_order(price, "bpi_reversal")
        elif hold_time >= self.params["max_hold_sec"]:
            log.info(f"[{self.stock_code}] Hold timeout: {hold_time:.0f}s >= {self.params['max_hold_sec']}s")
            self._place_sell_order(price, "timeout")

    def _place_sell_order(self, price: float, reason: str) -> None:
        pnl_pct = (price - self.buy_price) / self.buy_price if self.buy_price else 0
        hold_time = time.time() - self._hold_start - self._hold_paused
        log.info(f"[{self.stock_code}] Placing sell order: reason={reason}, qty={self.buy_qty}, "
                 f"price={price}, buy_price={self.buy_price}, pnl={pnl_pct:+.2%}, hold={hold_time:.0f}s")
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
            log.info(f"[{self.stock_code}] Buy filled: {quantity}@{price} "
                     f"(ordered@{self.buy_order_price}, total={price * quantity:,.0f}원)")
            self._set_state(WorkerState.HOLDING)
        elif side == "SELL" and self.state == WorkerState.SELLING:
            self.sell_price = price
            self.sell_qty = quantity
            self.hold_seconds = time.time() - self._hold_start - self._hold_paused
            self.pnl_pct = (self.sell_price - self.buy_price) / self.buy_price
            self.pnl_amount = (self.sell_price - self.buy_price) * self.sell_qty
            log.info(f"[{self.stock_code}] Sell filled: {quantity}@{price}, "
                     f"pnl={self.pnl_pct:+.2%} ({self.pnl_amount:+,.0f}원), "
                     f"hold={self.hold_seconds:.0f}s, reason={self.sell_reason}")
            self._set_state(WorkerState.DONE)

    def cancel(self, reason: str = "") -> None:
        self.sell_reason = reason
        self._set_state(WorkerState.CANCELLED)
