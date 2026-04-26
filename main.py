"""
SysTrader - News Scalping Automated Trading System
Entry point: COM STA main loop + uvicorn thread + Telegram threads

Requires: 32-bit Python, CYBOS Plus connected, admin privileges
"""
from __future__ import annotations
import logging
import os
import sys
import time

log = logging.getLogger("systrader")


def _disable_quick_edit():
    """Disable Quick Edit Mode to prevent console click from pausing the process."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        ENABLE_QUICK_EDIT = 0x0040
        ENABLE_EXTENDED_FLAGS = 0x0080
        mode.value = (mode.value & ~ENABLE_QUICK_EDIT) | ENABLE_EXTENDED_FLAGS
        kernel32.SetConsoleMode(handle, mode.value)
    except Exception:
        pass


def main():
    _disable_quick_edit()

    # Crash diagnostics: dump native traceback on segfault / fatal Python error.
    # Captures BUY-order STA crashes that previously died silently.
    import faulthandler
    faulthandler.enable(file=sys.stderr, all_threads=True)

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
    from src.web.context import _app_context
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

    balance = None
    executions_fetcher = None
    if connection.is_connected and account:
        from src.com.balance import CybosBalance
        from src.com.executions import CybosExecutions
        balance = CybosBalance(connection, account.account_number, account.goods_code)
        executions_fetcher = CybosExecutions(connection, account.account_number, account.goods_code)

    # 6. Stock tick manager
    stock_mst = StockMst(connection)
    from src.com.chart import CybosChart
    chart_fetcher = CybosChart(connection)

    def get_stock_info(code):
        return stock_mst.request(code)

    stock_cur_manager = StockCurManager(on_tick=lambda code, data: engine.on_tick(code, data))

    # 7. Trading engine
    def handle_order(order_type, code, qty, price):
        # Defer to main-loop CommandQueue. Calling COM (BlockRequest) directly here
        # would re-enter COM from a tick event handler (StockCur OnReceived) and
        # crash the process silently. The "place_order" handler runs on the main
        # thread between tick events, which is the only safe time to call BlockRequest.
        command_queue.put("place_order", {
            "order_type": order_type, "code": code, "qty": qty, "price": price,
        })

    def cancel_order(order_num: int, code: str, qty: int) -> None:
        try:
            order.cancel(order_num, code, qty)
        except Exception as e:
            log.warning(f"Cancel order failed: {e}")

    engine = TradingEngine(
        db=db, event_bus=event_bus,
        order_func=handle_order,
        stock_info_func=get_stock_info,
        subscribe_tick_func=stock_cur_manager.subscribe,
        unsubscribe_tick_func=stock_cur_manager.unsubscribe,
    )
    engine.set_balance(balance)
    engine.set_cancel_func(cancel_order)
    if executions_fetcher:
        engine.set_executions_fetcher(executions_fetcher)

    # Wire news -> engine (queued to main thread for COM safety)
    import queue as _queue
    _news_queue: _queue.Queue = _queue.Queue()
    event_bus.subscribe("news_detected", lambda data: _news_queue.put(data))

    # Log ALL news (CYBOS disclosures + Telegram messages) to DB for post-market keyword analysis
    _news_log_queue: _queue.Queue = _queue.Queue()
    event_bus.subscribe("news_feed", lambda data: _news_log_queue.put(data))

    # 7b. CYBOS conclusion (fill) events
    conclusion_mgr = None
    if connection.is_connected and order:
        from src.com.conclusion import ConclusionManager

        def on_conclusion(data):
            code = data["code"]
            engine.on_fill(code, data["side"], data["price"], data["quantity"])

        conclusion_mgr = ConclusionManager(callback=on_conclusion)
        try:
            conclusion_mgr.start()
        except Exception as e:
            log.warning(f"CpConclusion subscribe failed (will rely on balance polling): {e}")
            conclusion_mgr = None

    # 8. CYBOS news source — instantiate but don't subscribe; engine_start triggers subscription.
    cybos_news = None
    if connection.is_connected:
        try:
            cybos_news = CybosNewsSource(event_bus, code_manager)
        except Exception as e:
            log.error(f"CYBOS news source init failed: {e}")

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

    # 9b. Telegram 2FA code dialog
    if telegram_news:
        import threading
        import tkinter as tk
        from tkinter import simpledialog

        def _show_code_dialog(data):
            if not data.get("pending"):
                return
            def _ask():
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                code = simpledialog.askstring(
                    "Telegram 인증",
                    "텔레그램 인증 코드를 입력하세요:",
                    parent=root,
                )
                root.destroy()
                if code and telegram_news:
                    telegram_news.submit_auth_code(code.strip())
                    log.info("Telegram auth code submitted")
            threading.Thread(target=_ask, daemon=True).start()

        event_bus.subscribe("telegram_code_pending", _show_code_dialog)

    # 10. Telegram alert bot
    alert_bot = None
    if settings.telegram_bot.token:
        alert_bot = AlertBot(settings.telegram_bot.token, settings.telegram_bot.chat_id)
        alert_bot.start()
        event_bus.subscribe("buy_filled", alert_bot.on_buy_filled)
        event_bus.subscribe("sell_filled", alert_bot.on_sell_filled)
        event_bus.subscribe("trade_done", alert_bot.on_trade_done)

    # 11. News buffer for API
    register_news_buffer(event_bus)

    # 12. Start web server — use the shared module-level dict so subsequent updates
    # to context (from main thread) are visible to web routes via get_context().
    context = _app_context
    context.update({
        "db": db, "event_bus": event_bus, "command_queue": command_queue,
        "connection": connection, "account": account, "engine": engine, "balance": balance,
        "telegram_news": telegram_news, "settings": settings,
        "settings_path": settings_path, "log_dir": settings.logging.dir,
        # Cached COM state (refreshed from main thread; web reads safely)
        "cybos_connected": connection.is_connected if connection else False,
        "server_type": connection.get_server_type() if connection and connection.is_connected else "",
        "account_number": account.account_number if account else "",
    })
    start_server(context, settings.web.host, settings.web.port)

    # 13. Command handler
    def handle_command(cmd, params):
        nonlocal cybos_news
        if cmd == "engine_start":
            engine.start()
            # Lazy-init cybos_news if CYBOS connected after server startup
            if cybos_news is None and connection and connection.is_connected:
                try:
                    cybos_news = CybosNewsSource(event_bus, code_manager)
                    log.info("CYBOS news source lazy-initialized")
                except Exception as e:
                    log.error(f"CYBOS news source init failed: {e}")
            # Start news subscription (subscribe COM, enable telegram forwarding)
            if cybos_news:
                try:
                    cybos_news.start()
                except Exception as e:
                    log.error(f"CYBOS news subscribe failed: {e}")
            if telegram_news:
                telegram_news.set_active(True)
            return {"status": "ok"}
        elif cmd == "engine_stop":
            engine.stop()
            # Stop news subscription
            if cybos_news:
                try:
                    cybos_news.stop()
                except Exception as e:
                    log.error(f"CYBOS news unsubscribe failed: {e}")
            if telegram_news:
                telegram_news.set_active(False)
            return {"status": "ok"}
        elif cmd == "launch_cybos":
            import ctypes, os
            exe_path = settings.cybos.exe_path
            work_dir = os.path.dirname(exe_path)
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "open", exe_path, "/prj:cp", work_dir, 1
            )
            if rc <= 32:
                return {"status": "error", "message": f"ShellExecute failed (code={rc})"}
            return {"status": "ok"}
        elif cmd == "send_daily_summary":
            if not alert_bot:
                return {"status": "error", "message": "alert_bot not configured"}
            target_date = params.get("date") or time.strftime("%Y-%m-%d")
            trades_today = db.trades.list(date=target_date, limit=500)
            alert_bot.send_daily_summary(trades_today, target_date)
            return {"status": "ok"}
        elif cmd == "place_order":
            order_type = params["order_type"]
            code = params["code"]
            qty = params["qty"]
            price = params["price"]
            attempts = 3 if order_type.startswith("SELL") else 1
            last_err = None
            for i in range(attempts):
                try:
                    if order_type == "BUY":
                        result = order.buy_limit(code, qty, price)
                        w = engine.workers.get(code)
                        if w and isinstance(result, dict):
                            w.buy_order_num = result.get("order_num")
                    elif order_type == "SELL_MARKET":
                        order.sell_market(code, qty)
                    log.info(f"[ENGINE] Order submitted: {order_type} {code} {qty}@{price}")
                    return {"status": "ok"}
                except Exception as e:
                    last_err = e
                    log.warning(f"[ENGINE] Order attempt {i+1}/{attempts} failed for {code}: {e}")
                    if i + 1 < attempts:
                        time.sleep(0.5 * (i + 1))
            log.error(f"[ENGINE] Order FAILED after {attempts} attempts for {code}: {last_err}")
            w = engine.workers.get(code)
            if w and order_type == "BUY":
                w.cancel(f"buy_error: {last_err}")
            elif order_type != "BUY":
                log.warning(f"[ENGINE] SELL failure — worker stays in SELLING, will retry via polling")
            return {"status": "error", "message": str(last_err)}
        elif cmd == "emergency_sell_all":
            # Stop engine first so no new buys enter while we liquidate
            try:
                engine.stop()
            except Exception as e:
                log.warning(f"[EMERGENCY] engine.stop failed: {e}")
            from src.engine.worker import WorkerState
            holding = [w for w in engine.workers.values()
                       if w.state == WorkerState.HOLDING]
            log.critical(f"[EMERGENCY] Sell-all triggered: {len(holding)} holdings to liquidate")
            sold = 0
            for w in holding:
                try:
                    price = w._last_price or w.buy_price or 0
                    w._place_sell_order(price, "emergency_sell_all")
                    sold += 1
                except Exception as e:
                    log.error(f"[EMERGENCY] Sell failed for {w.stock_code}: {e}")
            event_bus.publish("emergency_sell_all", {"count": sold})
            return {"status": "ok", "count": sold}
        elif cmd == "fetch_chart":
            code = params.get("code", "")
            interval = params.get("interval", "m")
            period = int(params.get("period", 1))
            count = int(params.get("count", 200))
            if not connection.is_connected:
                return {"status": "error", "message": "CYBOS not connected"}
            try:
                rows = chart_fetcher.get_chart(code, interval, period, count)
                return {"status": "ok", "data": rows}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "unknown_command"}

    command_queue.register_handler(handle_command)

    # 14. Main loop - COM message pump
    stop_event = win32event.CreateEvent(None, 0, 0, None)
    log.info("Entering main loop. Web UI: http://localhost:%d", settings.web.port)

    last_status_poll = 0.0
    last_fill_poll = 0.0
    last_snapshot_poll = 0.0
    last_daily_summary_date = ""  # tracks date the daily summary was sent
    balance_error_count = 0  # suppresses repeated warnings during CYBOS maintenance windows

    try:
        while True:
            handles = [stop_event]
            rc = win32event.MsgWaitForMultipleObjects(
                handles, 0, 50, win32event.QS_ALLEVENTS
            )
            if rc == win32event.WAIT_OBJECT_0:
                break
            elif rc == win32event.WAIT_OBJECT_0 + len(handles):
                pythoncom.PumpWaitingMessages()

            if command_queue.has_pending():
                command_queue.process()

            # Process queued news on main thread (COM-safe)
            while not _news_queue.empty():
                try:
                    news_data = _news_queue.get_nowait()
                    engine.on_news(news_data)
                except _queue.Empty:
                    break
                except Exception as e:
                    log.error(f"News processing error: {e}")

            # Log all news_feed events to news_events table with current price snapshot
            while not _news_log_queue.empty():
                try:
                    nd = _news_log_queue.get_nowait()
                    code = nd.get("stock_code") or ""
                    name = nd.get("stock_name") or ""
                    title = nd.get("text") or ""
                    source = nd.get("source") or ""
                    category = nd.get("category") or ""
                    price = None
                    if code and connection and connection.is_connected:
                        try:
                            info = stock_mst.request(code)
                            if info:
                                price = float(info.get("current_price") or 0) or None
                        except Exception:
                            pass
                    db.news_events.insert(source, category, code, name, title[:500], price)
                except _queue.Empty:
                    break
                except Exception as e:
                    log.debug(f"News log error: {e}")

            # Refresh CYBOS connection state (main thread = COM STA)
            now = time.time()
            if now - last_status_poll >= 2.0:
                last_status_poll = now
                try:
                    is_conn = connection.is_connected if connection else False
                    prev = context.get("cybos_connected", False)
                    context["cybos_connected"] = is_conn
                    if is_conn:
                        if not context.get("server_type"):
                            context["server_type"] = connection.get_server_type()
                        # Lazy init account/order/balance on first connect
                        if account is None:
                            try:
                                from src.com.account import CybosAccount
                                from src.com.order import CybosOrder
                                from src.com.balance import CybosBalance
                                account = CybosAccount()
                                account.init()
                                order = CybosOrder(connection, account.account_number, account.goods_code)
                                balance = CybosBalance(connection, account.account_number, account.goods_code)
                                engine.set_balance(balance)
                                context["account"] = account
                                context["balance"] = balance
                                context["account_number"] = account.account_number
                                log.info(f"Account initialized post-connect: {account.account_number}")
                            except Exception as e:
                                log.error(f"Post-connect account init failed: {e}")
                    if is_conn != prev:
                        event_bus.publish("cybos_status", {
                            "connected": is_conn,
                            "server_type": context.get("server_type", ""),
                        })
                        log.info(f"CYBOS connection: {is_conn}")
                except Exception as e:
                    log.debug(f"Status poll error: {e}")

            # Snapshot post-news prices (5m/15m/30m) for keyword analysis
            if now - last_snapshot_poll >= 30.0 and connection and connection.is_connected:
                last_snapshot_poll = now
                for offset_field, after_sec in (("price_5m", 300), ("price_15m", 900), ("price_30m", 1800)):
                    try:
                        rows = db.news_events.needs_snapshot(offset_field, after_sec, limit=5)
                    except Exception as e:
                        log.debug(f"Snapshot query error: {e}")
                        continue
                    for row in rows:
                        try:
                            info = stock_mst.request(row["stock_code"])
                            if not info:
                                continue
                            cur_price = float(info.get("current_price") or 0)
                            if cur_price <= 0:
                                continue
                            ret = (cur_price - row["price_at_news"]) / row["price_at_news"]
                            return_field = offset_field.replace("price_", "return_")
                            db.news_events.update(row["id"], **{
                                offset_field: cur_price,
                                return_field: ret,
                            })
                        except Exception as e:
                            log.debug(f"Snapshot fetch error for {row.get('stock_code')}: {e}")

                # Post-sell snapshots (5m/15m/30m/60m) for missed-gain analysis
                for offset_field, after_sec in (("price_after_5m", 300), ("price_after_15m", 900),
                                                  ("price_after_30m", 1800), ("price_after_60m", 3600)):
                    try:
                        rows = db.trades.needs_postsell_snapshot(offset_field, after_sec, limit=5)
                    except Exception as e:
                        log.debug(f"Postsell query error: {e}")
                        continue
                    for row in rows:
                        try:
                            info = stock_mst.request(row["stock_code"])
                            if not info:
                                continue
                            cur_price = float(info.get("current_price") or 0)
                            if cur_price <= 0:
                                continue
                            ret = (cur_price - row["sell_price"]) / row["sell_price"]
                            return_field = offset_field.replace("price_", "return_")
                            db.trades.update(row["id"], **{
                                offset_field: cur_price,
                                return_field: ret,
                            })
                        except Exception as e:
                            log.debug(f"Postsell snapshot error for {row.get('stock_code')}: {e}")

                # Track running max price after sell (every poll cycle, for trades within last hour)
                try:
                    max_rows = db.trades.needs_max_tracking(limit=10)
                except Exception as e:
                    max_rows = []
                    log.debug(f"Max tracking query error: {e}")
                for row in max_rows:
                    try:
                        info = stock_mst.request(row["stock_code"])
                        if not info:
                            continue
                        cur_price = float(info.get("current_price") or 0)
                        if cur_price <= 0:
                            continue
                        cur_max = row.get("max_price_after_sell")
                        if cur_max is None or cur_price > cur_max:
                            sell_price = row["sell_price"]
                            max_ret = (cur_price - sell_price) / sell_price if sell_price else 0
                            db.trades.update(row["id"],
                                max_price_after_sell=cur_price,
                                max_return_after_sell=max_ret,
                                max_time_after_sell=time.strftime("%Y-%m-%dT%H:%M:%S"))
                    except Exception as e:
                        log.debug(f"Max snapshot error for {row.get('stock_code')}: {e}")

            # Daily summary at 15:40 (after KOSPI close 15:30). Once per day.
            # Bot readiness: AlertBot.start() spawns thread → loop init takes a moment.
            today_str = time.strftime("%Y-%m-%d")
            now_hm = time.strftime("%H%M")
            if (alert_bot and alert_bot._bot and alert_bot._loop
                    and "1540" <= now_hm < "2359"
                    and last_daily_summary_date != today_str):
                try:
                    trades_today = db.trades.list(date=today_str, limit=500)
                    alert_bot.send_daily_summary(trades_today, today_str)
                    last_daily_summary_date = today_str
                    log.info(f"Daily summary sent for {today_str}")
                except Exception as e:
                    log.error(f"Daily summary send failed: {e}")

            # Balance-based fill detection + worker timeouts + holdings cache
            # Only poll while engine is running (avoids CpTd6033 errors during pre-market).
            if now - last_fill_poll >= 2.0:
                last_fill_poll = now
                bal = context.get("balance")
                # Tick-independent timeout checks
                try:
                    engine.check_worker_timeouts()
                except Exception as e:
                    log.debug(f"Timeout check error: {e}")
                if bal is not None and engine.running:
                    try:
                        engine.check_pending_fills(bal)
                    except Exception as e:
                        log.debug(f"Fill poll error: {e}")
                    # Refresh holdings cache for /api/reconciliation (read from web thread)
                    try:
                        context["holdings_cache"] = bal.get_holdings()
                        context["holdings_cache_time"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                        if balance_error_count > 0:
                            log.info(f"Holdings cache recovered after {balance_error_count} errors")
                            balance_error_count = 0
                    except Exception as e:
                        balance_error_count += 1
                        # Log first error only; stay silent during sustained outages (maintenance window)
                        if balance_error_count == 1:
                            log.warning(f"Holdings cache refresh failed (suppressing repeats): {e}")

    except KeyboardInterrupt:
        log.info("Shutdown requested")
    finally:
        log.info("Shutting down...")
        engine.stop()
        stock_cur_manager.unsubscribe_all()
        if cybos_news:
            cybos_news.stop()
        if conclusion_mgr:
            conclusion_mgr.stop()
        db.close()
        log.info("SysTrader stopped")


if __name__ == "__main__":
    main()
