"""Tests for CpConclusion (real-time fill events) handler."""
import sys
from unittest.mock import MagicMock, patch

sys.modules.setdefault("win32com", MagicMock())
sys.modules.setdefault("win32com.client", MagicMock())
sys.modules.setdefault("pythoncom", MagicMock())

from src.com.conclusion import ConclusionHandler, ConclusionManager


class TestConclusionHandler:
    def test_conclusion_handler_dispatches_buy_fill(self):
        callback = MagicMock()
        ConclusionManager.callback = callback

        handler = ConclusionHandler.__new__(ConclusionHandler)
        handler.GetHeaderValue = lambda idx: {
            0: "체결", 1: "A005930", 5: 50000, 6: 10, 12: "2", 14: 12345
        }.get(idx, "")

        handler.OnReceived()

        callback.assert_called_once_with({
            "code": "A005930",
            "side": "BUY",
            "price": 50000,
            "quantity": 10,
            "order_num": 12345,
        })

    def test_conclusion_handler_dispatches_sell_fill(self):
        callback = MagicMock()
        ConclusionManager.callback = callback

        handler = ConclusionHandler.__new__(ConclusionHandler)
        handler.GetHeaderValue = lambda idx: {
            0: "체결", 1: "A035720", 5: 120000, 6: 5, 12: "1", 14: 99999
        }.get(idx, "")

        handler.OnReceived()

        callback.assert_called_once_with({
            "code": "A035720",
            "side": "SELL",
            "price": 120000,
            "quantity": 5,
            "order_num": 99999,
        })

    def test_conclusion_handler_ignores_non_conclusion(self):
        callback = MagicMock()
        ConclusionManager.callback = callback

        handler = ConclusionHandler.__new__(ConclusionHandler)
        handler.GetHeaderValue = lambda idx: {
            0: "접수", 1: "A005930", 5: 50000, 6: 10, 12: "2", 14: 12345
        }.get(idx, "")

        handler.OnReceived()

        callback.assert_not_called()


class TestConclusionManager:
    @patch("src.com.conclusion.win32com.client.DispatchWithEvents")
    def test_manager_start_stop(self, mock_dispatch):
        mock_obj = MagicMock()
        mock_dispatch.return_value = mock_obj

        cb = MagicMock()
        mgr = ConclusionManager(callback=cb)
        mgr.start()

        mock_dispatch.assert_called_once_with("DsCbo1.CpConclusion", ConclusionHandler)
        mock_obj.Subscribe.assert_called_once()

        mgr.stop()
        mock_obj.Unsubscribe.assert_called_once()
