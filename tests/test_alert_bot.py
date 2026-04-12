import sys
from unittest.mock import MagicMock, patch

sys.modules.setdefault("telegram", MagicMock())

from src.telegram.bot import AlertBot


def make_bot():
    bot = AlertBot(token="test_token", chat_id=12345)
    bot.send = MagicMock()
    return bot


class TestOnTradeDone:
    def test_on_trade_done_sends_summary(self):
        bot = make_bot()
        bot.on_trade_done({"name": "삼성전자", "code": "A005930", "trade_id": 1, "pnl_pct": 0.02})

        bot.send.assert_called_once()
        msg = bot.send.call_args[0][0]
        assert "삼성전자" in msg
        assert "A005930" in msg
        assert "+2.00%" in msg

    def test_on_trade_done_negative_pnl(self):
        bot = make_bot()
        bot.on_trade_done({"name": "카카오", "code": "A035720", "trade_id": 2, "pnl_pct": -0.015})

        bot.send.assert_called_once()
        msg = bot.send.call_args[0][0]
        assert "-1.50%" in msg
