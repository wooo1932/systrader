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

    balance = None
    if connection.is_connected and account:
        from src.com.balance import CybosBalance
        balance = CybosBalance(connection, account.account_number, account.goods_code)

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

    # Wire news -> engine (queued to main thread for COM safety)
    import queue as _queue
    _news_queue: _queue.Queue = _queue.Queue()
    event_bus.subscribe("news_detected", lambda data: _news_queue.put(data))

    # 7b. CYBOS conclusion (fill) events
    conclusion_mgr = None
    if connection.is_connected and order:
        from src.com.conclusion import ConclusionManager

        def on_conclusion(data):
            code = data["code"]
            engine.on_fill(code, data["side"], data["price"], data["quantity"])

        conclusion_mgr = ConclusionManager(callback=on_conclusion)
        conclusion_mgr.start()

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

    # 12. Start web server
    context = {
        "db": db, "event_bus": event_bus, "command_queue": command_queue,
        "connection": connection, "account": account, "engine": engine, "balance": balance,
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

    # 14. Main loop - COM message pump
    stop_event = win32event.CreateEvent(None, 0, 0, None)
    log.info("Entering main loop. Web UI: http://localhost:%d", settings.web.port)

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
