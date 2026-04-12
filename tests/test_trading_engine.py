from __future__ import annotations
import time
from unittest.mock import MagicMock
from src.database import Database
from src.core.event_bus import EventBus
from src.engine.trading_engine import TradingEngine


def _make_engine():
    """Create a TradingEngine with in-memory DB and mock functions."""
    db = Database(":memory:")
    db.ensure_schema()
    event_bus = EventBus()

    order_func = MagicMock()
    stock_info_func = MagicMock(return_value={
        "market_cap": 100_000_000_000,
        "change_pct": 10.0,
        "current_price": 50000,
        "upper_limit_price": 65000,
    })
    subscribe_func = MagicMock()
    unsubscribe_func = MagicMock()

    engine = TradingEngine(
        db=db,
        event_bus=event_bus,
        order_func=order_func,
        stock_info_func=stock_info_func,
        subscribe_tick_func=subscribe_func,
        unsubscribe_tick_func=unsubscribe_func,
    )
    engine.start()
    return engine, db


def _simulate_trade(engine, code="A005930", name="Samsung",
                    buy_price=50000, sell_price=51000, buy_qty=20):
    """Simulate a full trade cycle: on_news -> on_fill BUY -> on_fill SELL."""
    from src.engine.worker import WorkerState

    news = {
        "code": code,
        "name": name,
        "source": "cybos",
        "channel": "news",
        "title": "test news",
    }
    engine.on_news(news)

    worker = engine.workers[code]
    # Force worker into BUYING state so on_fill BUY is accepted
    worker.state = WorkerState.BUYING
    engine.on_fill(code, "BUY", buy_price, buy_qty)

    # Worker is now HOLDING after BUY fill; force into SELLING
    worker.sell_reason = "bpi_reversal"
    worker.state = WorkerState.SELLING
    engine.on_fill(code, "SELL", sell_price, buy_qty)

    return worker


class TestDailyStatsAggregation:
    def test_single_trade_populates_daily_stats(self):
        engine, db = _make_engine()

        _simulate_trade(engine, buy_price=50000, sell_price=51000, buy_qty=20)

        today = time.strftime("%Y-%m-%d")
        rows = db.daily_stats.get_range(date_from=today, date_to=today)
        assert len(rows) == 1

        stats = rows[0]
        assert stats["total_trades"] == 1
        assert stats["win_count"] == 1
        assert stats["loss_count"] == 0
        assert stats["total_pnl"] == (51000 - 50000) * 20  # 20000
        assert stats["best_trade_pnl"] == (51000 - 50000) * 20
        assert stats["worst_trade_pnl"] == (51000 - 50000) * 20
        assert stats["win_rate"] == 1.0

    def test_two_trades_accumulate_stats(self):
        engine, db = _make_engine()

        # Trade 1: win (sell > buy)
        _simulate_trade(engine, code="A005930", name="Samsung",
                        buy_price=50000, sell_price=51000, buy_qty=20)

        # Trade 2: loss (sell < buy)
        _simulate_trade(engine, code="A000660", name="SK Hynix",
                        buy_price=60000, sell_price=58000, buy_qty=10)

        today = time.strftime("%Y-%m-%d")
        rows = db.daily_stats.get_range(date_from=today, date_to=today)
        assert len(rows) == 1

        stats = rows[0]
        assert stats["total_trades"] == 2
        assert stats["win_count"] == 1
        assert stats["loss_count"] == 1

        win_pnl = (51000 - 50000) * 20   # 20000
        loss_pnl = (58000 - 60000) * 10  # -20000
        assert stats["total_pnl"] == win_pnl + loss_pnl  # 0
        assert stats["best_trade_pnl"] == win_pnl
        assert stats["worst_trade_pnl"] == loss_pnl
        assert stats["win_rate"] == 0.5
