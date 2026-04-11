import time
import pytest
from unittest.mock import MagicMock
from src.engine.worker import StockWorker, WorkerState


@pytest.fixture
def params():
    return {
        "entry_up_ticks": 3,
        "entry_buy_ratio": 0.6,
        "entry_timeout_sec": 60,
        "buy_tick_offset": 1,
        "bet_amount": 1_000_000,
        "fill_timeout_sec": 10,
        "bpi_short_window": 10,
        "bpi_long_window": 30,
        "bpi_sell_threshold": 0.4,
        "stoploss_pct": -0.03,
        "maxdrop_pct": -0.02,
        "max_hold_sec": 300,
        "vi_detect_sec": 3.0,
    }


@pytest.fixture
def worker(params):
    on_order = MagicMock()
    on_state_change = MagicMock()
    w = StockWorker(
        stock_code="A005930", stock_name="삼성전자",
        news_source="telegram", news_text="test",
        params=params, on_order=on_order, on_state_change=on_state_change,
    )
    return w


def make_tick(price, bid_or_ask="buy", volume=100):
    return {"price": price, "volume": volume, "bid_or_ask": bid_or_ask,
            "timestamp": time.time()}


class TestScreeningPhase:
    def test_initial_state_is_screening(self, worker):
        assert worker.state == WorkerState.SCREENING

    def test_entry_on_consecutive_up_ticks(self, worker):
        worker.on_tick(make_tick(10000))
        worker.on_tick(make_tick(10050))
        worker.on_tick(make_tick(10100))
        worker.on_tick(make_tick(10150))
        worker.on_tick(make_tick(10200))
        assert worker.state == WorkerState.BUYING

    def test_no_entry_without_enough_up_ticks(self, worker):
        worker.on_tick(make_tick(10000))
        worker.on_tick(make_tick(10050))
        worker.on_tick(make_tick(10000))
        assert worker.state == WorkerState.SCREENING

    def test_no_entry_without_buy_ratio(self, worker):
        worker.on_tick(make_tick(10000, "sell"))
        worker.on_tick(make_tick(10050, "sell"))
        worker.on_tick(make_tick(10100, "sell"))
        worker.on_tick(make_tick(10150, "sell"))
        assert worker.state == WorkerState.SCREENING

    def test_entry_timeout_cancels(self, worker, params):
        params["entry_timeout_sec"] = 0
        worker.params = params
        worker._screen_start = time.time() - 1
        worker.on_tick(make_tick(10000))
        assert worker.state == WorkerState.CANCELLED


class TestHoldingPhase:
    def _enter_holding(self, worker):
        worker.state = WorkerState.HOLDING
        worker.buy_price = 10000
        worker.buy_qty = 100
        worker.highest_price = 10000
        worker._hold_start = time.time()
        worker._last_tick_time = time.time()
        worker._init_bpi()

    def test_stoploss_triggers_sell(self, worker):
        self._enter_holding(worker)
        worker.on_tick(make_tick(9600))
        assert worker.state == WorkerState.SELLING

    def test_maxdrop_triggers_sell(self, worker):
        self._enter_holding(worker)
        worker.highest_price = 11000
        worker.on_tick(make_tick(10700))
        assert worker.state == WorkerState.SELLING

    def test_timeout_triggers_sell(self, worker, params):
        self._enter_holding(worker)
        params["max_hold_sec"] = 0
        worker.params = params
        worker._hold_start = time.time() - 1
        worker.on_tick(make_tick(10000))
        assert worker.state == WorkerState.SELLING

    def test_bpi_reversal_triggers_sell(self, worker):
        self._enter_holding(worker)
        for _ in range(30):
            worker.bpi.add(is_buy=True)
        for _ in range(10):
            worker.bpi.add(is_buy=False)
        worker.on_tick(make_tick(10000, "sell"))
        assert worker.state == WorkerState.SELLING

    def test_updates_highest_price(self, worker):
        self._enter_holding(worker)
        worker.on_tick(make_tick(10500))
        assert worker.highest_price == 10500

    def test_vi_detection_resets_bpi(self, worker, params):
        self._enter_holding(worker)
        params["vi_detect_sec"] = 0.01
        worker.params = params
        worker._last_tick_time = time.time() - 1
        worker.on_tick(make_tick(10000))
        assert len(worker.bpi._short) == 0


class TestFillCallback:
    def test_buy_fill_transitions_to_holding(self, worker):
        worker.state = WorkerState.BUYING
        worker.on_fill(side="BUY", price=10050, quantity=99)
        assert worker.state == WorkerState.HOLDING
        assert worker.buy_price == 10050
        assert worker.buy_qty == 99

    def test_sell_fill_transitions_to_done(self, worker):
        worker.state = WorkerState.SELLING
        worker.buy_price = 10000
        worker.buy_qty = 100
        worker._hold_start = time.time() - 10
        worker.on_fill(side="SELL", price=10300, quantity=100)
        assert worker.state == WorkerState.DONE
        assert worker.pnl_pct == pytest.approx(0.03, abs=0.001)
