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
    "max_market_cap": "10000000000000",
    "min_change_pct": "5.0",
    "max_change_pct": "28.0",
    "entry_up_ticks": "3",
    "entry_timeout_sec": "90",
    "entry_buy_ratio": "0.6",
    "buy_tick_offset": "1",
    "bet_amount": "1000000",
    "fill_timeout_sec": "10",
    "bpi_short_window": "10",
    "bpi_long_window": "30",
    "bpi_sell_threshold": "0.3",
    "stoploss_pct": "-0.05",
    "maxdrop_pct": "-0.02",
    "max_hold_sec": "300",
    "vi_detect_sec": "3.0",
    "selling_timeout_sec": "60",
    "min_hold_sec": "60",  # min hold before BPI/maxdrop can fire (stoploss always active)
    "trailing_stop_pct": "-0.015",  # trigger when price falls X% from highest (active after min_hold)
    "trailing_activate_pct": "0.01",  # activate trailing only after +1% gain reached
    "buy_cutoff_hhmm": "1515",  # no new buys after this time (15 min buffer before 15:30 close)
    "market_open_hhmm": "0900",   # trading hours start (KOSPI/KOSDAQ)
    "market_close_hhmm": "1530",  # trading hours end
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
        self._balance = None
        self._cancel_func = None
        self._executions_fetcher = None

    def set_balance(self, balance) -> None:
        self._balance = balance

    def set_cancel_func(self, fn) -> None:
        self._cancel_func = fn

    def set_executions_fetcher(self, fetcher) -> None:
        self._executions_fetcher = fetcher

    def _refresh_executions(self, worker) -> None:
        """Replace local execution records with broker's authoritative data via CpTd5341."""
        if self._executions_fetcher is None or not worker.trade_id:
            return
        try:
            real = self._executions_fetcher.get_today_by_stock(worker.stock_code)
            if not real:
                return
            # Filter to executions matching our known order_num(s) when possible.
            relevant = [r for r in real if r.get("order_num") == worker.buy_order_num] or real
            # Replace: delete existing, insert real
            self.db.execute("DELETE FROM executions WHERE trade_id = ?", (worker.trade_id,))
            for r in relevant:
                side = "buy" if r["side"] == "BUY" else "sell"
                self.db.executions.insert(
                    worker.trade_id, side, r["price"], r["quantity"],
                    r.get("executed_at") or time.strftime("%H:%M:%S")
                )
            log.info(f"[ENGINE] Executions refreshed from broker: {worker.stock_code} "
                     f"({len(relevant)} records)")
        except Exception as e:
            log.debug(f"[ENGINE] Executions refresh failed for {worker.stock_code}: {e}")

    def _snapshot_holding_qty(self, code: str) -> int:
        qty, _ = self._snapshot_holding(code)
        return qty

    def _snapshot_holding(self, code: str) -> tuple[int, float]:
        """Returns (quantity, avg_price) for the given code from broker holdings."""
        if self._balance is None:
            return 0, 0.0
        try:
            holdings = self._balance.get_holdings()
            for h in holdings:
                if h.get("code") == code:
                    return int(h.get("quantity") or 0), float(h.get("price") or 0)
        except Exception as e:
            log.debug(f"[ENGINE] snapshot error for {code}: {e}")
        return 0, 0.0

    def _reconcile_broker_holdings(self) -> None:
        """Broker-first reconciliation at engine start.
        Uses actual broker positions (CpTd6033) as ground truth. For every broker holding:
          1. Find a matching open trade (holding/screening/buying) in DB — attach to it if exists.
          2. Otherwise create a synthetic trade record (untracked orphan).
          3. Create a HOLDING worker; mark force_liquidate if buy_date < today.
        After this, also recover any in-DB 'selling'/'buying' trades that still need monitoring.
        """
        if self._balance is None:
            log.warning("[ENGINE] Reconcile: balance not ready; falling back to DB recovery only")
            self._recover_pending_workers()
            return
        try:
            broker = self._balance.get_holdings()
        except Exception as e:
            log.warning(f"[ENGINE] Reconcile: broker query failed ({e}); falling back to DB recovery")
            self._recover_pending_workers()
            return

        today = time.strftime("%Y-%m-%d")
        broker_by_code = {h["code"]: h for h in broker if (h.get("quantity") or 0) > 0}
        handled_codes: set[str] = set()

        if not broker_by_code:
            log.info("[ENGINE] Reconcile: no broker positions")
        else:
            log.info(f"[ENGINE] Reconcile: {len(broker_by_code)} broker positions found")

        for code, h in broker_by_code.items():
            qty = int(h.get("quantity") or 0)
            broker_avg = float(h.get("price") or 0)
            name = h.get("name") or ""

            # Try to find matching DB trade (most recent holding/screening/buying)
            matched = None
            for status in ("holding", "selling", "buying", "screening"):
                rows = self.db.trades.list(status=status, limit=100)
                for r in rows:
                    if r["stock_code"] == code:
                        matched = r
                        break
                if matched:
                    break

            if matched:
                trade_id = matched["id"]
                buy_price = float(matched.get("buy_price") or broker_avg or 0)
                buy_qty = int(matched.get("buy_qty") or qty)
                buy_time = matched.get("buy_time") or ""
                params = {}
                try:
                    params = json.loads(matched.get("parameter_snapshot") or "{}")
                except Exception:
                    pass
                if not params:
                    params = self.get_typed_params()
                log.info(f"[ENGINE] Reconcile: attaching to trade {trade_id} for {code} (qty={qty})")
                # Normalize DB status to 'holding' for consistent handling
                self.db.trades.update(trade_id, status="holding",
                                      buy_price=buy_price, buy_qty=qty if matched.get("buy_qty") is None else buy_qty,
                                      stock_name=matched.get("stock_name") or name)
            else:
                # Orphan — create synthetic trade record
                params = self.get_typed_params()
                trade_id = self.db.trades.create(
                    stock_code=code, stock_name=name,
                    news_source="broker_reconcile", news_channel="",
                    news_text="(reconciled from broker holding)",
                    parameter_snapshot=json.dumps(params),
                )
                buy_price = broker_avg
                buy_qty = qty
                buy_time = ""
                self.db.trades.update(trade_id, status="holding",
                                      buy_price=buy_price, buy_qty=qty,
                                      buy_time="")
                log.warning(f"[ENGINE] Reconcile: created synthetic trade {trade_id} for orphan {code} qty={qty} @ {broker_avg:.0f}")

            # Create worker in HOLDING state
            try:
                worker = StockWorker(
                    stock_code=code, stock_name=name,
                    news_source="", news_text="",
                    params=params,
                    on_order=self._handle_order,
                    on_state_change=self._handle_state_change,
                )
                worker.trade_id = trade_id
                worker.buy_price = int(round(buy_price)) if buy_price else 0
                worker.buy_qty = qty
                worker.highest_price = worker.buy_price
                worker.state = WorkerState.HOLDING

                # Restore hold_start from DB buy_time
                buy_date = ""
                if buy_time:
                    try:
                        from datetime import datetime
                        buy_dt = datetime.fromisoformat(buy_time)
                        worker._hold_start = buy_dt.timestamp()
                        buy_date = buy_dt.strftime("%Y-%m-%d")
                    except Exception:
                        worker._hold_start = time.time()
                else:
                    worker._hold_start = time.time()

                worker._last_tick_time = time.time()
                worker._init_bpi()

                # Force liquidate if not bought today
                if not buy_date or buy_date < today:
                    worker.force_liquidate = True
                    log.info(f"[{code}] Overnight/orphan — will force-sell at market open")

                self.workers[code] = worker
                self._subscribe_tick(code)
                handled_codes.add(code)
            except Exception as e:
                log.error(f"[ENGINE] Worker creation failed for {code}: {e}")

        # Clean up DB: any 'holding' trades not matched to broker → mark cancelled
        stale_holdings = [r for r in self.db.trades.list(status="holding", limit=100)
                          if r["stock_code"] not in handled_codes]
        for r in stale_holdings:
            self.db.trades.update(r["id"], status="cancelled",
                                  sell_reason="reconcile_no_broker_position")
            log.info(f"[ENGINE] Reconcile: stale DB holding {r['stock_code']} marked cancelled (not in broker)")

        # Lastly, recover 'selling'/'buying' trades that still need monitoring
        self._recover_pending_workers(skip_codes=handled_codes)

    def _recover_pending_workers(self, skip_codes: set = None) -> None:
        """On engine start, recover workers for trades stuck in buying/selling/holding from a previous run."""
        skip_codes = skip_codes or set()
        rows = []
        for status in ("holding", "selling", "buying"):
            rows.extend(self.db.trades.list(status=status, limit=200))
        rows = [r for r in rows if r["stock_code"] not in skip_codes]
        if not rows:
            return
        log.info(f"[ENGINE] Found {len(rows)} pending trade(s) to recover (after reconcile skip)")
        for row in rows:
            code = row["stock_code"]
            if code in self.workers:
                continue
            try:
                params = json.loads(row.get("parameter_snapshot") or "{}")
                if not params:
                    params = self.get_typed_params()
                current_qty = self._snapshot_holding_qty(code)
                buy_price = float(row.get("buy_price") or 0)
                buy_qty = int(row.get("buy_qty") or 0)
                buy_order_price = float(row.get("buy_order_price") or 0)
                highest_price = float(row.get("highest_price") or buy_price or 0)

                worker = StockWorker(
                    stock_code=code, stock_name=row.get("stock_name") or "",
                    news_source=row.get("news_source") or "",
                    news_text=row.get("news_text") or "",
                    params=params,
                    on_order=self._handle_order,
                    on_state_change=self._handle_state_change,
                )
                worker.trade_id = row["id"]
                worker.buy_price = buy_price
                worker.buy_qty = buy_qty
                worker.buy_order_price = buy_order_price
                worker.highest_price = highest_price

                status = row["status"]
                if status == "holding":
                    if current_qty >= buy_qty and buy_qty > 0:
                        worker.state = WorkerState.HOLDING
                        # Restore original hold_start from DB buy_time so max_hold_sec works correctly
                        buy_time_str = row.get("buy_time") or ""
                        buy_date = ""
                        try:
                            from datetime import datetime
                            buy_dt = datetime.fromisoformat(buy_time_str)
                            worker._hold_start = buy_dt.timestamp()
                            buy_date = buy_dt.strftime("%Y-%m-%d")
                        except Exception:
                            worker._hold_start = time.time()
                        worker._last_tick_time = time.time()
                        worker._init_bpi()
                        # If the buy happened on a previous day, mark for immediate liquidation
                        # at the next market-hours check (no matter what max_hold_sec is).
                        today = time.strftime("%Y-%m-%d")
                        if buy_date and buy_date < today:
                            worker.force_liquidate = True
                        self.workers[code] = worker
                        self._subscribe_tick(code)
                        elapsed = time.time() - worker._hold_start
                        carry_note = " — OVERNIGHT, will force-sell at market open" if worker.force_liquidate else ""
                        log.info(f"[ENGINE] Recovered HOLDING {code} qty={buy_qty} "
                                 f"(broker={current_qty}, elapsed={elapsed:.0f}s, buy_date={buy_date}){carry_note}")
                    else:
                        self.db.trades.update(row["id"], status="cancelled",
                                               sell_reason="recovery_no_position")
                        log.warning(f"[ENGINE] Recovery: HOLDING {code} no broker position "
                                    f"(broker={current_qty}, expected={buy_qty}) -> cancelled")
                elif status == "selling":
                    if buy_qty > 0 and current_qty < buy_qty:
                        # Sell already filled (current dropped below pre-sell holdings).
                        sold_qty = buy_qty - current_qty if current_qty > 0 else buy_qty
                        sell_price = worker._last_price or buy_price or buy_order_price
                        worker.sell_price = sell_price
                        worker.sell_qty = sold_qty
                        worker.pnl_pct = (sell_price - buy_price) / buy_price if buy_price else 0
                        worker.pnl_amount = (sell_price - buy_price) * sold_qty
                        worker.hold_seconds = 0
                        self.db.trades.update(row["id"],
                            sell_qty=sold_qty, sell_price=sell_price,
                            sell_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                            sell_reason=row.get("sell_reason") or "recovery_sold",
                            pnl_pct=worker.pnl_pct, pnl_amount=worker.pnl_amount,
                            highest_price=highest_price, hold_seconds=0,
                            status="done")
                        log.info(f"[ENGINE] Recovery: SELLING {code} confirmed sold "
                                 f"(broker={current_qty}, expected={buy_qty}, sold={sold_qty}@{sell_price})")
                    else:
                        # Sell did not complete; resume monitoring.
                        worker.state = WorkerState.SELLING
                        worker.pre_order_qty = current_qty
                        worker._hold_start = time.time()
                        worker._last_tick_time = time.time()
                        self.workers[code] = worker
                        self._subscribe_tick(code)
                        log.info(f"[ENGINE] Recovered SELLING {code} qty={buy_qty} "
                                 f"(broker={current_qty}, awaiting fill)")
                elif status == "buying":
                    order_qty = int(row.get("buy_order_qty") or 0)
                    if order_qty <= 0:
                        # No recorded order qty (legacy). Cancel safely.
                        self.db.trades.update(row["id"], status="cancelled",
                                               sell_reason="recovery_buying_no_qty")
                        log.warning(f"[ENGINE] Recovery: BUYING {code} aborted (no order qty recorded)")
                    else:
                        # We know the order qty. Resume monitoring with snapshot.
                        worker.buy_order_qty = order_qty
                        worker.state = WorkerState.BUYING
                        worker.pre_order_qty = current_qty  # baseline; future fills detected via delta
                        self.workers[code] = worker
                        self._subscribe_tick(code)
                        log.info(f"[ENGINE] Recovered BUYING {code} order_qty={order_qty} "
                                 f"(broker={current_qty}, awaiting fill)")
            except Exception as e:
                log.error(f"[ENGINE] Recovery error for {code}: {e}")

    def start(self) -> None:
        self._load_params()
        self._ensure_default_params()
        self.running = True
        try:
            self._reconcile_broker_holdings()
        except Exception as e:
            log.error(f"[ENGINE] Reconciliation failed: {e}")
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
                     "bpi_long_window", "max_hold_sec", "selling_timeout_sec",
                     "min_hold_sec"}
        float_keys = {"min_change_pct", "max_change_pct", "entry_buy_ratio",
                       "bpi_sell_threshold", "stoploss_pct", "maxdrop_pct",
                       "vi_detect_sec", "trailing_stop_pct", "trailing_activate_pct"}
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

        # Market-hours window for new buys.
        now_hhmm = time.strftime("%H%M")
        market_open = self.get_param("market_open_hhmm") or "0900"
        cutoff = self.get_param("buy_cutoff_hhmm") or "1515"
        if now_hhmm < market_open:
            log.info(f"[ENGINE] News skipped (pre-market, before {market_open}): {code} ({name})")
            return
        if now_hhmm >= cutoff:
            log.info(f"[ENGINE] News skipped (after buy cutoff {cutoff}): {code} ({name})")
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
        # Ticks are kept in worker memory only (worker._ticks) for screening logic.
        # No DB persistence — Analysis page fetches chart via CpSysDib.StockChart on demand.
        worker = self.workers.get(code)
        if not worker:
            return
        worker.on_tick(tick_data)

    def on_fill(self, code: str, side: str, price: float, quantity: int) -> None:
        # Korean stock prices are integer KRW — round once here so executions table matches trades.
        price_int = int(round(price))
        log.info(f"[ENGINE] Fill received: {side} {code} {quantity}@{price_int}")
        worker = self.workers.get(code)
        if not worker:
            log.warning(f"[ENGINE] Fill for unknown worker: {code}")
            return
        if worker.trade_id:
            self.db.executions.insert(
                worker.trade_id, side, price_int, quantity,
                time.strftime("%Y-%m-%dT%H:%M:%S")
            )
        worker.on_fill(side, price_int, quantity)

    def _handle_order(self, order_type: str, code: str, qty: int, price: int) -> None:
        log.info(f"[ENGINE] Placing order: {order_type} {code} {qty}@{price}")
        # Retry with backoff. Sell failures MUST NOT leave a HOLDING position orphaned,
        # so we retry up to 3 times. Buy failures fall through to cancel (safe default).
        attempts = 3 if order_type.startswith("SELL") else 1
        last_err = None
        for i in range(attempts):
            try:
                self._order_func(order_type, code, qty, price)
                log.info(f"[ENGINE] Order submitted: {order_type} {code} {qty}@{price}")
                return
            except Exception as e:
                last_err = e
                log.warning(f"[ENGINE] Order attempt {i+1}/{attempts} failed for {code}: {e}")
                if i + 1 < attempts:
                    time.sleep(0.5 * (i + 1))  # 0.5s, 1.0s backoff
        log.error(f"[ENGINE] Order FAILED after {attempts} attempts for {code}: {last_err}")
        worker = self.workers.get(code)
        if not worker:
            return
        if order_type == "BUY":
            # BUY failure → cancel screening/buying worker (no position was opened)
            worker.cancel(f"buy_error: {last_err}")
        else:
            # SELL failure → keep worker in SELLING, let check_pending_fills re-issue.
            # Also arm the selling_timeout_sec backstop.
            log.warning(f"[ENGINE] SELL failure — worker stays in SELLING, will retry via polling")

    def _handle_state_change(self, worker: StockWorker,
                              old: WorkerState, new: WorkerState) -> None:
        log.info(f"Worker {worker.stock_code}: {old.value} -> {new.value}")

        self.event_bus.publish("worker_state", {
            "code": worker.stock_code, "name": worker.stock_name,
            "state": new.value, "trade_id": worker.trade_id,
        })

        if new in (WorkerState.BUYING, WorkerState.SELLING) and worker.trade_id:
            updates = {"status": new.value}
            if new == WorkerState.BUYING and worker.buy_order_qty:
                updates["buy_order_qty"] = worker.buy_order_qty
                updates["buy_order_price"] = worker.buy_order_price
            self.db.trades.update(worker.trade_id, **updates)
            # Snapshot pre-order holding qty + avg price so balance polling can compute exact fill price
            qty, avg = self._snapshot_holding(worker.stock_code)
            worker.pre_order_qty = qty
            worker.pre_order_avg_price = avg
            log.info(f"[ENGINE] Pre-order snapshot {worker.stock_code}: qty={qty}, avg={avg}")

        if new == WorkerState.HOLDING and worker.trade_id:
            self.db.trades.update(worker.trade_id,
                buy_price=worker.buy_price, buy_qty=worker.buy_qty,
                buy_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                buy_order_price=worker.buy_order_price,
                highest_price=worker.buy_price,
                entry_condition=getattr(worker, "entry_condition", ""),
                status="holding")
            self.event_bus.publish("buy_filled", {
                "code": worker.stock_code, "name": worker.stock_name,
                "price": worker.buy_price, "qty": worker.buy_qty,
                "order_price": worker.buy_order_price,
                "total_amount": worker.buy_price * worker.buy_qty,
                "news_source": worker.news_source,
                "news_text": worker.news_text,
                "time": time.strftime("%H:%M:%S"),
                "trade_id": worker.trade_id,
            })

        elif new == WorkerState.DONE and worker.trade_id:
            outcome = "win" if (worker.pnl_amount or 0) > 0 else ("loss" if (worker.pnl_amount or 0) < 0 else "even")
            self.db.trades.update(worker.trade_id,
                sell_price=worker.sell_price, sell_qty=worker.sell_qty,
                sell_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                sell_reason=worker.sell_reason,
                pnl_pct=worker.pnl_pct, pnl_amount=worker.pnl_amount,
                highest_price=worker.highest_price,
                hold_seconds=worker.hold_seconds,
                outcome=outcome, status="done")
            # Replace our estimated executions with actual broker records (accurate fill prices)
            self._refresh_executions(worker)
            self.event_bus.publish("sell_filled", {
                "code": worker.stock_code, "name": worker.stock_name,
                "price": worker.sell_price, "qty": worker.sell_qty,
                "buy_price": worker.buy_price,
                "total_amount": worker.sell_price * worker.sell_qty,
                "pnl_pct": worker.pnl_pct, "pnl_amount": worker.pnl_amount,
                "highest_price": worker.highest_price,
                "hold_seconds": worker.hold_seconds,
                "reason": worker.sell_reason,
                "time": time.strftime("%H:%M:%S"),
                "trade_id": worker.trade_id,
            })
            self.event_bus.publish("trade_done", {
                "code": worker.stock_code, "name": worker.stock_name,
                "buy_price": worker.buy_price, "sell_price": worker.sell_price,
                "qty": worker.sell_qty,
                "pnl_pct": worker.pnl_pct, "pnl_amount": worker.pnl_amount,
                "hold_seconds": worker.hold_seconds,
                "reason": worker.sell_reason,
                "trade_id": worker.trade_id,
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

    def check_worker_timeouts(self) -> None:
        """Tick-independent timeout check (call from main loop).
        Also includes tick-less stoploss for HOLDING workers — if the stock stopped ticking
        while price is crashing, relying on tick-driven stoploss is dangerous. We poll the
        current price via stock_mst for all HOLDING workers as a safety net.

        Market-hours gate: HOLDING/SELLING actions that require order placement are skipped
        outside trading hours (orders would fail anyway). At market open, the first run of
        this method will pick up overnight carry-over positions and sell them.
        """
        try:
            timeout_sec = float(self.get_param("selling_timeout_sec") or 60)
        except (TypeError, ValueError):
            timeout_sec = 60.0
        try:
            stoploss_pct = float(self.get_param("stoploss_pct") or -0.05)
        except (TypeError, ValueError):
            stoploss_pct = -0.05
        now_hhmm = time.strftime("%H%M")
        market_open = self.get_param("market_open_hhmm") or "0900"
        market_close = self.get_param("market_close_hhmm") or "1530"
        in_market = market_open <= now_hhmm <= market_close

        for w in list(self.workers.values()):
            try:
                if w.state == WorkerState.SCREENING:
                    # Screening timeout can run anytime (cancels stale pre-market screens).
                    w.check_screening_timeout()
                elif w.state == WorkerState.HOLDING:
                    if not in_market:
                        continue  # Defer sell decisions until market opens
                    # Overnight carry-over: force-sell immediately (regardless of max_hold / pnl).
                    if w.force_liquidate:
                        try:
                            info = self._stock_info_func(w.stock_code) if self._stock_info_func else None
                            cur_price = float(info.get("current_price") or 0) if info else 0
                        except Exception:
                            cur_price = 0
                        cur_price = cur_price or w._last_price or w.buy_price
                        log.warning(f"[{w.stock_code}] Force-liquidating overnight position at {cur_price}")
                        w._last_price = cur_price
                        w.force_liquidate = False  # prevent re-firing while SELL in flight
                        w._place_sell_order(cur_price, "overnight_liquidate")
                        continue
                    # Tick-less stoploss safety net: poll current price and force stoploss.
                    if w.buy_price > 0 and self._stock_info_func:
                        try:
                            info = self._stock_info_func(w.stock_code)
                            if info:
                                cur_price = float(info.get("current_price") or 0)
                                if cur_price > 0:
                                    pnl_pct = (cur_price - w.buy_price) / w.buy_price
                                    if pnl_pct <= stoploss_pct:
                                        log.warning(f"[{w.stock_code}] Tick-less stoploss triggered: "
                                                    f"pnl={pnl_pct:+.2%} (buy={w.buy_price}, now={cur_price})")
                                        w._last_price = cur_price
                                        w._place_sell_order(cur_price, "stoploss_tickless")
                                        continue
                        except Exception as e:
                            log.debug(f"[ENGINE] Price poll error for {w.stock_code}: {e}")
                    # Overnight carry-over: if buy_time is from a previous day or hold_time
                    # exceeds max_hold_sec, check_holding_timeout will fire a sell.
                    w.check_holding_timeout()
                elif w.state == WorkerState.SELLING:
                    # Selling timeout handled anytime (may clear stuck orders).
                    w.check_selling_timeout(timeout_sec)
            except Exception as e:
                log.error(f"[ENGINE] Timeout check error for {w.stock_code}: {e}")

    def check_pending_fills(self, balance) -> None:
        """Balance-polling fallback for simulated trading where CpConclusion may not fire.
        Uses pre-order qty snapshot to detect delta (avoids picking up pre-existing positions).
        Also reconciles HOLDING workers if broker added more shares (delayed buy fills).
        """
        if balance is None:
            return
        # Include HOLDING to catch post-fill additional buy fills (shallow simulator order books)
        pending = [w for w in self.workers.values()
                   if w.state in (WorkerState.BUYING, WorkerState.SELLING, WorkerState.HOLDING)]
        if not pending:
            return
        try:
            holdings = balance.get_holdings()
        except Exception as e:
            log.debug(f"[ENGINE] balance poll error: {e}")
            return
        held_map = {h["code"]: h for h in holdings}
        for w in pending:
            held = held_map.get(w.stock_code)
            current_qty = int(held.get("quantity") or 0) if held else 0
            current_avg = float(held.get("price") or 0) if held else 0
            if w.state == WorkerState.BUYING:
                delta = current_qty - w.pre_order_qty
                if delta > 0:
                    # Compute exact fill price from delta capital:
                    # fill_price = (current_qty*current_avg - pre_qty*pre_avg) / delta
                    pre_value = w.pre_order_qty * w.pre_order_avg_price
                    cur_value = current_qty * current_avg
                    new_capital = cur_value - pre_value
                    if delta > 0 and new_capital > 0:
                        price = new_capital / delta
                    else:
                        price = current_avg or w.buy_order_price or w._last_price or 0
                    if price > 0:
                        log.info(f"[ENGINE] Fill detected via balance: BUY {w.stock_code} "
                                 f"{delta}@{price:.2f} (pre={w.pre_order_qty}@{w.pre_order_avg_price:.0f}, "
                                 f"now={current_qty}@{current_avg:.0f})")
                        # Cancel any unfilled remainder before transitioning to HOLDING.
                        # Otherwise the broker may keep filling our limit order over time, leading
                        # to untracked late fills (see SGC에너지 case 2026-04-21).
                        remaining = w.buy_order_qty - delta
                        if remaining > 0 and w.buy_order_num and self._cancel_func:
                            log.info(f"[ENGINE] Cancelling unfilled remainder: "
                                     f"{w.stock_code} order_num={w.buy_order_num} qty={remaining}")
                            try:
                                self._cancel_func(w.buy_order_num, w.stock_code, remaining)
                            except Exception as e:
                                log.warning(f"[ENGINE] Cancel call failed: {e}")
                        self.on_fill(w.stock_code, "BUY", price, delta)
            elif w.state == WorkerState.HOLDING:
                # Detect any delayed buy fills (broker qty grew beyond what we tracked).
                expected = w.pre_order_qty + w.buy_qty
                if current_qty > expected and current_avg > 0:
                    extra = current_qty - expected
                    new_buy_qty = current_qty - w.pre_order_qty
                    log.warning(f"[ENGINE] Late buy fill detected for {w.stock_code}: "
                                f"+{extra} shares (was {w.buy_qty}, now {new_buy_qty}). "
                                f"buy_price {w.buy_price:.0f}->{current_avg:.0f}")
                    w.buy_qty = new_buy_qty
                    w.buy_price = int(round(current_avg))
                    if w.trade_id:
                        try:
                            self.db.trades.update(w.trade_id,
                                buy_qty=w.buy_qty, buy_price=w.buy_price)
                        except Exception as e:
                            log.error(f"[ENGINE] DB update for late fill failed: {e}")
            elif w.state == WorkerState.SELLING:
                delta = w.pre_order_qty - current_qty
                if delta > 0:
                    fill_price = float(w._last_price or w.buy_price or 0)
                    if fill_price > 0:
                        # Accumulate this partial fill (handles shallow simulator order books)
                        w.cumulative_sold_qty += delta
                        w.cumulative_sold_value += delta * fill_price
                        log.info(f"[ENGINE] Partial sell fill {w.stock_code}: "
                                 f"{delta}@{fill_price} (cum={w.cumulative_sold_qty}, broker_left={current_qty})")
                        # Slide the snapshot baseline so subsequent polls detect new partials
                        w.pre_order_qty = current_qty
                        # Reset re-sell gate: original SELL_MARKET is still actively filling.
                        # Only re-issue after a true stall (no fills for the gap window).
                        w._last_resell_at = time.time()
                # Compare OUR cumulative sold vs what we meant to sell (buy_qty).
                # Never use current_qty>0 as "still selling" — broker may hold pre-existing
                # positions unrelated to this trade (→ false re-sell, "매도가능수량 부족").
                if w.cumulative_sold_qty >= w.buy_qty and w.buy_qty > 0:
                    vwap = w.cumulative_sold_value / w.cumulative_sold_qty if w.cumulative_sold_qty else 0
                    log.info(f"[ENGINE] Sell complete {w.stock_code}: "
                             f"sold={w.cumulative_sold_qty}@{vwap:.2f} (vwap)")
                    self.on_fill(w.stock_code, "SELL", vwap, w.cumulative_sold_qty)
                elif w.state == WorkerState.SELLING:
                    remaining_to_sell = w.buy_qty - w.cumulative_sold_qty
                    # 30s gap: original SELL_MARKET reserves shares in the broker queue.
                    # Re-issuing while it's still active → "매도가능수량 부족". Wait long
                    # enough that either the original fills or the broker truly drops it.
                    # selling_timeout (90s) is the final safety net for stuck orders.
                    if remaining_to_sell > 0 and time.time() - w._last_resell_at >= 30.0:
                        w._last_resell_at = time.time()
                        log.info(f"[ENGINE] Re-issuing SELL_MARKET for remaining {remaining_to_sell} "
                                 f"shares of {w.stock_code} (cum_sold={w.cumulative_sold_qty}, target={w.buy_qty})")
                        try:
                            self._order_func("SELL_MARKET", w.stock_code, remaining_to_sell, 0)
                        except Exception as e:
                            log.warning(f"[ENGINE] Re-sell failed for {w.stock_code}: {e}")
                            # Likely original order still active — back off another 30s on top
                            w._last_resell_at = time.time() + 30

    @property
    def active_worker_count(self) -> int:
        return sum(1 for w in self.workers.values()
                   if w.state not in (WorkerState.DONE, WorkerState.CANCELLED))
