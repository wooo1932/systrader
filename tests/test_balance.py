import sys
from unittest.mock import MagicMock, patch

sys.modules.setdefault("win32com", MagicMock())
sys.modules.setdefault("win32com.client", MagicMock())
sys.modules.setdefault("pythoncom", MagicMock())

from src.com.balance import CybosBalance


def _make_balance():
    conn = MagicMock()
    return CybosBalance(conn, "12345678", "1")


def test_get_holdings_parses_response():
    balance = _make_balance()
    with patch("src.com.balance.win32com.client.Dispatch") as mock_dispatch:
        mock_obj = MagicMock()
        mock_dispatch.return_value = mock_obj
        mock_obj.BlockRequest.return_value = 0
        mock_obj.GetDibStatus.return_value = 0
        mock_obj.GetHeaderValue.side_effect = lambda idx: {7: 2}[idx]
        mock_obj.GetDataValue.side_effect = lambda col, row: {
            (0, 0): "A005930", (1, 0): "삼성전자", (7, 0): 50000, (9, 0): 10,
            (0, 1): "A035720", (1, 1): "카카오",   (7, 1): 30000, (9, 1): 5,
        }[(col, row)]

        holdings = balance.get_holdings()

    assert len(holdings) == 2
    assert holdings[0] == {"code": "A005930", "name": "삼성전자", "price": 50000, "quantity": 10}
    assert holdings[1] == {"code": "A035720", "name": "카카오", "price": 30000, "quantity": 5}


def test_get_holdings_empty():
    balance = _make_balance()
    with patch("src.com.balance.win32com.client.Dispatch") as mock_dispatch:
        mock_obj = MagicMock()
        mock_dispatch.return_value = mock_obj
        mock_obj.BlockRequest.return_value = 0
        mock_obj.GetDibStatus.return_value = 0
        mock_obj.GetHeaderValue.side_effect = lambda idx: {7: 0}[idx]

        holdings = balance.get_holdings()

    assert holdings == []
