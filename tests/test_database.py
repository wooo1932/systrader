import os
import pytest
from src.database import Database


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    database = Database(db_path)
    database.ensure_schema()
    return database


class TestTradeRepository:
    def test_create_trade(self, db):
        trade_id = db.trades.create(
            stock_code="A005930", stock_name="삼성전자",
            news_source="telegram", news_channel="test_ch",
            news_text="삼성전자 관련 뉴스"
        )
        assert trade_id > 0

    def test_get_trade(self, db):
        trade_id = db.trades.create(
            stock_code="A005930", stock_name="삼성전자",
            news_source="telegram"
        )
        trade = db.trades.get(trade_id)
        assert trade["stock_code"] == "A005930"
        assert trade["status"] == "screening"

    def test_list_trades_with_status_filter(self, db):
        db.trades.create(stock_code="A005930", stock_name="삼성전자", news_source="t")
        db.trades.create(stock_code="A000660", stock_name="SK하이닉스", news_source="t")
        db.trades.update(1, status="done")
        result = db.trades.list(status="screening")
        assert len(result) == 1
        assert result[0]["stock_code"] == "A000660"

    def test_update_trade_buy(self, db):
        tid = db.trades.create(stock_code="A005930", stock_name="삼성전자", news_source="t")
        db.trades.update(tid, buy_price=70000, buy_qty=14, buy_time="2026-04-11T10:00:00",
                         buy_order_price=70050, status="holding")
        trade = db.trades.get(tid)
        assert trade["buy_price"] == 70000
        assert trade["status"] == "holding"


class TestParameterRepository:
    def test_get_all_empty(self, db):
        params = db.params.get_all()
        assert params == []

    def test_upsert_and_get(self, db):
        db.params.upsert("max_holdings", "3", "system")
        params = db.params.get_all()
        assert len(params) == 1
        assert params[0]["key"] == "max_holdings"
        assert params[0]["value"] == "3"

    def test_upsert_records_history(self, db):
        db.params.upsert("max_holdings", "3", "system")
        db.params.upsert("max_holdings", "5", "user")
        history = db.params.get_history()
        assert len(history) == 1
        assert history[0]["old_value"] == "3"
        assert history[0]["new_value"] == "5"


class TestTickRepository:
    def test_insert_and_get_ticks(self, db):
        tid = db.trades.create(stock_code="A005930", stock_name="삼성전자", news_source="t")
        db.ticks.insert(tid, "A005930", 70000, 100, "buy", "2026-04-11T10:00:00.000")
        db.ticks.insert(tid, "A005930", 70050, 50, "sell", "2026-04-11T10:00:00.100")
        ticks = db.ticks.get_by_trade(tid)
        assert len(ticks) == 2
        assert ticks[0]["price"] == 70000


class TestNewsChannelRepository:
    def test_create_and_list(self, db):
        db.channels.create("https://t.me/test", "Test Channel")
        channels = db.channels.list()
        assert len(channels) == 1
        assert channels[0]["channel_name"] == "Test Channel"
        assert channels[0]["enabled"] == 1

    def test_toggle(self, db):
        db.channels.create("https://t.me/test", "Test")
        db.channels.toggle(1)
        channels = db.channels.list()
        assert channels[0]["enabled"] == 0

    def test_delete(self, db):
        db.channels.create("https://t.me/test", "Test")
        db.channels.delete(1)
        assert db.channels.list() == []


class TestExecutionRepository:
    def test_insert_and_get(self, db):
        tid = db.trades.create(stock_code="A005930", stock_name="삼성전자", news_source="t")
        db.executions.insert(tid, "BUY", 70000, 14, "2026-04-11T10:00:00")
        execs = db.executions.get_by_trade(tid)
        assert len(execs) == 1
        assert execs[0]["side"] == "BUY"


class TestDailyStatsRepository:
    def test_upsert_and_get(self, db):
        db.daily_stats.upsert("2026-04-11", total_trades=5, win_count=3,
                               loss_count=2, win_rate=0.6, total_pnl=15000)
        stats = db.daily_stats.get_range(days=30)
        assert len(stats) == 1
        assert stats[0]["total_trades"] == 5

    def test_get_summary(self, db):
        db.daily_stats.upsert("2026-04-11", total_trades=5, win_count=3,
                               loss_count=2, win_rate=0.6, total_pnl=15000,
                               avg_pnl_pct=0.5)
        summary = db.daily_stats.get_summary()
        assert summary["total_trades"] == 5
