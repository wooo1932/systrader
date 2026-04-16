from __future__ import annotations
import logging
import win32com.client
from src.com.connection import CybosConnection

log = logging.getLogger(__name__)


class CybosBalance:
    def __init__(self, connection: CybosConnection, account: str, goods_code: str):
        self._conn = connection
        self._account = account
        self._goods_code = goods_code

    def get_holdings(self) -> list[dict]:
        self._conn.wait_if_limited(1)
        obj = win32com.client.Dispatch("CpTrade.CpTd6033")
        obj.SetInputValue(0, self._account)
        obj.SetInputValue(1, self._goods_code)
        obj.SetInputValue(2, 50)
        ret = obj.BlockRequest()
        if ret != 0:
            log.error(f"CpTd6033 BlockRequest failed: ret={ret}")
            return []
        if obj.GetDibStatus() != 0:
            log.error(f"CpTd6033 error: {obj.GetDibMsg1()}")
            return []
        count = obj.GetHeaderValue(7)
        holdings = []
        for i in range(count):
            holdings.append({
                "code": obj.GetDataValue(12, i),
                "name": obj.GetDataValue(0, i),
                "price": obj.GetDataValue(17, i),
                "quantity": obj.GetDataValue(7, i),
            })
        return holdings
