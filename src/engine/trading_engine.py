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
    "max_market_cap": "50000000000000",
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

        log.info(f"[ENGINE] Processing news: {code} ({name}) - {news_data.get('title', '')[:60]}")

        params = self.get_typed_params()
        info = self._stock_info_func(code)
        if not info:
            log.warning(f"[ENGINE] Stock info not available for {code}")
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
            log.info(f"[ENGINE] Screener rejected {code} ({name}): {result.reason} "
                     f"(change_pct={info['change_pct']}, market_cap={info['market_cap']}, price={info['current_price']})")
            return

        params["upper_limit_price"] = info["upper_limit_price"]
        log.info(f"[ENGINE] Screener passed {code} ({name}), creating worker...")
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

        self._subscribe_tick(code)
        log.info(f"[ENGINE] Worker created for {code} ({name}), trade_id={trade_id}, subscribing ticks")
        self.event_bus.publish("worker_state", {
            "code": code, "name": name, "state": "screening", "trade_id": trade_id
        })

    def on_tick(self, code: str, tick_data: dict) -> None:
        worker = self.workers.get(code)
        if not worker:
            return
        if worker.trade_id:
            self.db.ticks.insert(
                worker.trade_id, code, tick_data["price"],
                tick_data["volume"], tick_data["bid_or_ask"],
                tick_data.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%S"))
            )
        worker.on_tick(tick_data)

    def on_fill(self, code: str, side: str, price: float, quantity: int) -> None:
        log.info(f"[ENGINE] Fill received: {side} {code} {quantity}@{price}")
        worker = self.workers.get(code)
        if not worker:
            log.warning(f"[ENGINE] Fill for unknown worker: {code}")
            return
        if worker.trade_id:
            self.db.executions.insert(
                worker.trade_id, side, price, quantity,
                time.strftime("%Y-%m-%dT%H:%M:%S")
            )
        worker.on_fill(side, price, quantity)

    def _handle_order(self, order_type: str, code: str, qty: int, price: int) -> None:
        log.info(f"[ENGINE] Placing order: {order_type} {code} {qty}@{price}")
        try:
            self._order_func(order_type, code, qty, price)
            log.info(f"[ENGINE] Order submitted: {order_type} {code} {qty}@{price}")
        except Exception as e:
            log.error(f"[ENGINE] Order failed for {code}: {e}")
            worker = self.workers.get(code)
            if worker:
                worker.cancel(f"order_error: {e}")

    def _handle_state_change(self, worker: StockWorker,
                              old: WorkerState, new: WorkerState) -> None:
        log.info(f"Worker {worker.stock_code}: {old.value} -> {new.value}")

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
                "code": worker.stock_code, "name": worker.stock_name,
                "trade_id": worker.trade_id, "pnl_pct": worker.pnl_pct,
            })
            self._update_daily_stats(worker)
            self._unsubscribe_tick(worker.stock_code)

        elif new == WorkerState.CANCELLED and worker.trade_id:
            self.db.trades.update(worker.trade_id,
                sell_reason=worker.sell_reason, status="cancelled")
            self._unsubscribe_tick(worker.stock_code)

    def _update_daily_stats(self, worker) -> None:
        today = time.strftime("%Y-%m-%d")
        rows = self.db.daily_stats.get_range(date_from=today, date_to=today)

        pnl_amount = worker.pnl_amount
        pnl_pct = worker.pnl_pct
        hold_seconds = worker.hold_seconds
        is_win = pnl_amount > 0

        if rows:
            s = rows[0]
            total_trades = s["total_trades"] + 1
            win_count = s["win_count"] + (1 if is_win else 0)
            loss_count = s["loss_count"] + (0 if is_win else 1)
            total_pnl = s["total_pnl"] + pnl_amount
            # Recalculate average pnl_pct as running average
            avg_pnl_pct = (s["avg_pnl_pct"] * s["total_trades"] + pnl_pct) / total_trades
            best_trade_pnl = max(s["best_trade_pnl"], pnl_amount)
            worst_trade_pnl = min(s["worst_trade_pnl"], pnl_amount)
            avg_hold_seconds = (s["avg_hold_seconds"] * s["total_trades"] + hold_seconds) / total_trades
            win_rate = win_count / total_trades if total_trades > 0 else 0.0
        else:
            total_trades = 1
            win_count = 1 if is_win else 0
            loss_count = 0 if is_win else 1
            total_pnl = pnl_amount
            avg_pnl_pct = pnl_pct
            best_trade_pnl = pnl_amount
            worst_trade_pnl = pnl_amount
            avg_hold_seconds = hold_seconds
            win_rate = 1.0 if is_win else 0.0

        self.db.daily_stats.upsert(today,
            total_trades=total_trades,
            win_count=win_count,
            loss_count=loss_count,
            win_rate=win_rate,
            total_pnl=total_pnl,
            avg_pnl_pct=avg_pnl_pct,
            best_trade_pnl=best_trade_pnl,
            worst_trade_pnl=worst_trade_pnl,
            avg_hold_seconds=avg_hold_seconds,
        )

    @property
    def active_worker_count(self) -> int:
        return sum(1 for w in self.workers.values()
                   if w.state not in (WorkerState.DONE, WorkerState.CANCELLED))
