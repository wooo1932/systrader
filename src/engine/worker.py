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
        self._screen_start_price: float = 0  # first observed price during screening
        self.entry_condition: str = ""  # which condition triggered the buy
        self._order_num: Optional[int] = None
        # Pre-order holdings snapshot (for balance-polling fill detection)
        self.pre_order_qty: int = 0
        self.pre_order_avg_price: float = 0
        # Quantity ordered (BUYING) — used for recovery and tracking
        self.buy_order_qty: int = 0
        # Broker order_num for cancellation (set after order placement returns)
        self.buy_order_num: Optional[int] = None
        # Overnight carry-over flag: force-liquidate on first market-hours check
        self.force_liquidate: bool = False
        # Time when sell order was placed (for SELLING timeout)
        self._selling_start: float = 0
        # Partial-fill accumulator for SELLING (multiple SELL_MARKET fills can happen)
        self.cumulative_sold_qty: int = 0
        self.cumulative_sold_value: float = 0.0
        self._last_resell_at: float = 0.0  # rate-limit re-issuing SELL_MARKET

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

    def check_screening_timeout(self) -> bool:
        """Tick-independent timeout check (callable from main loop). Returns True if timed out."""
        if self.state != WorkerState.SCREENING:
            return False
        elapsed = time.time() - self._screen_start
        if elapsed > self.params["entry_timeout_sec"]:
            log.info(f"[{self.stock_code}] Screening timeout after {elapsed:.1f}s "
                     f"(tick-less), ticks={len(self._ticks)}, consecutive_up={self._consecutive_up}")
            self._set_state(WorkerState.CANCELLED)
            return True
        return False

    def check_holding_timeout(self) -> bool:
        """Tick-independent max-hold timeout for HOLDING workers (e.g. when a stock stops
        trading / after market close). Triggers sell at last known price."""
        if self.state != WorkerState.HOLDING or not self._hold_start:
            return False
        max_hold = self.params.get("max_hold_sec", 300)
        hold_time = time.time() - self._hold_start - self._hold_paused
        if hold_time >= max_hold:
            price = self._last_price or self.buy_price
            log.info(f"[{self.stock_code}] Holding timeout (tick-less) after {hold_time:.0f}s "
                     f">= {max_hold}s, force-selling at {price}")
            self._place_sell_order(price, "timeout")
            return True
        return False

    def check_selling_timeout(self, timeout_sec: float = 60.0) -> bool:
        """Force-close SELLING workers stuck without fill (e.g., simulation orphan)."""
        if self.state != WorkerState.SELLING or not self._selling_start:
            return False
        elapsed = time.time() - self._selling_start
        if elapsed > timeout_sec:
            log.warning(f"[{self.stock_code}] Selling timeout after {elapsed:.1f}s, force-closing")
            # Treat as filled at last known price (best effort)
            sell_price = self._last_price or self.buy_price or 0
            self.sell_price = sell_price
            self.sell_qty = self.buy_qty
            self.hold_seconds = (time.time() - self._hold_start - self._hold_paused) if self._hold_start else 0
            self.pnl_pct = (sell_price - self.buy_price) / self.buy_price if self.buy_price else 0
            self.pnl_amount = (sell_price - self.buy_price) * self.sell_qty
            if not self.sell_reason:
                self.sell_reason = "selling_timeout"
            self._set_state(WorkerState.DONE)
            return True
        return False

    def _handle_screening(self, tick: dict, price: float) -> None:
        if self.check_screening_timeout():
            return

        if self._screen_start_price == 0:
            self._screen_start_price = price

        if self._last_price > 0 and price > self._last_price:
            self._consecutive_up += 1
        elif self._last_price > 0 and price < self._last_price:
            self._consecutive_up = 0

        buy_count = sum(1 for t in self._ticks if t["bid_or_ask"] == "buy")
        buy_ratio = buy_count / len(self._ticks) if self._ticks else 0

        # Cumulative gain since screening start
        gain_pct = ((price - self._screen_start_price) / self._screen_start_price * 100
                    if self._screen_start_price else 0)

        # Recent volume vs earlier volume (last 20 ticks vs prior 20)
        recent_vol_ratio = 0.0
        if len(self._ticks) >= 40:
            recent_vol = sum(t.get("volume", 0) for t in self._ticks[-20:])
            prior_vol = sum(t.get("volume", 0) for t in self._ticks[-40:-20])
            recent_vol_ratio = (recent_vol / prior_vol) if prior_vol > 0 else 0

        if len(self._ticks) % 20 == 0:
            log.info(f"[{self.stock_code}] Screening: price={price}, ticks={len(self._ticks)}, "
                     f"up={self._consecutive_up}/{self.params['entry_up_ticks']}, "
                     f"buy_ratio={buy_ratio:.2f}/{self.params['entry_buy_ratio']}, "
                     f"gain={gain_pct:+.2f}%, vol_ratio={recent_vol_ratio:.2f}")

        # Entry conditions. "momentum" (up_ticks + buy_ratio only, price-agnostic)
        # was removed 2026-04-23 after 37-trade review: win 33.3% / -316K over 9
        # trades, and in particular fired on stocks actively dropping (e.g.
        # 아이씨디 at gain=-1.78%) because ratios can look strong during selloffs.
        # price_breakout and volume_spike both require positive gain, so selloffs
        # are filtered out.
        ratio_thresh = self.params["entry_buy_ratio"]
        alt_ratio_thresh = max(0.50, ratio_thresh - 0.10)

        condition = ""
        if gain_pct >= 0.3 and buy_ratio >= alt_ratio_thresh:
            condition = "price_breakout"  # cumulative price gain
        elif recent_vol_ratio >= 1.5 and buy_ratio >= alt_ratio_thresh and gain_pct >= 0.1:
            condition = "volume_spike"  # volume burst with mild positive gain

        if condition:
            self.entry_condition = condition
            log.info(f"[{self.stock_code}] Entry signal [{condition}]! "
                     f"up={self._consecutive_up}, buy_ratio={buy_ratio:.2f}, "
                     f"gain={gain_pct:+.2f}%, vol_ratio={recent_vol_ratio:.2f}, price={price}")
            self._place_buy_order(price)

    def _place_buy_order(self, current_price: float) -> None:
        order_price = int(self.params.get("upper_limit_price", current_price))
        if order_price <= 0:
            order_price = current_price
        qty = self.params["bet_amount"] // current_price
        if qty <= 0:
            log.warning(f"[{self.stock_code}] Buy cancelled: qty=0 (bet={self.params['bet_amount']}, price={current_price})")
            self._set_state(WorkerState.CANCELLED)
            return
        self.buy_order_price = order_price
        self.buy_order_qty = qty
        log.info(f"[{self.stock_code}] Placing buy order: {qty}@{order_price}(upper_limit) "
                 f"(current={current_price}, bet={self.params['bet_amount']})")
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

        # Stoploss is always active (protect against catastrophic drops).
        # BPI / maxdrop / trailing / timeout require min_hold_sec elapsed first to avoid
        # premature exits on noise immediately after fill.
        min_hold = self.params.get("min_hold_sec", 60)
        high_pnl = (self.highest_price - self.buy_price) / self.buy_price if self.buy_price else 0
        trailing_activate = self.params.get("trailing_activate_pct", 0.01)
        trailing_stop = self.params.get("trailing_stop_pct", -0.015)
        if pnl_pct <= self.params["stoploss_pct"]:
            log.info(f"[{self.stock_code}] Stoploss triggered: pnl={pnl_pct:+.2%}")
            self._place_sell_order(price, "stoploss")
        elif hold_time < min_hold:
            return  # within minimum-hold grace window; only stoploss above can fire
        elif high_pnl >= trailing_activate and drop_pct <= trailing_stop:
            # Trailing stop: once we've locked in +1% gain, cut if price falls 1.5% from peak
            log.info(f"[{self.stock_code}] Trailing stop triggered: high_pnl={high_pnl:+.2%}, "
                     f"drop_from_high={drop_pct:+.2%}, price={price}")
            self._place_sell_order(price, "trailing_stop")
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
        self._selling_start = time.time()
        # Record this as the initial resell timestamp so check_pending_fills waits long enough
        # before trying to re-issue (prevents "매도가능수량 부족" spam while broker processes
        # the first order).
        self._last_resell_at = time.time()
        self._set_state(WorkerState.SELLING)
        self._on_order("SELL_MARKET", self.stock_code, self.buy_qty, 0)

    def on_fill(self, side: str, price: float, quantity: int) -> None:
        # Korean stock prices are integer KRW; round to avoid fractional display from
        # holdings-avg approximations.
        price = int(round(price))
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
            self.pnl_pct = (self.sell_price - self.buy_price) / self.buy_price if self.buy_price else 0
            self.pnl_amount = (self.sell_price - self.buy_price) * self.sell_qty
            log.info(f"[{self.stock_code}] Sell filled: {quantity}@{price}, "
                     f"pnl={self.pnl_pct:+.2%} ({self.pnl_amount:+,.0f}원), "
                     f"hold={self.hold_seconds:.0f}s, reason={self.sell_reason}")
            self._set_state(WorkerState.DONE)

    def cancel(self, reason: str = "") -> None:
        self.sell_reason = reason
        self._set_state(WorkerState.CANCELLED)
