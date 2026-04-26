from __future__ import annotations
import logging
import win32com.client
from src.com.connection import CybosConnection

log = logging.getLogger(__name__)


class CybosOrder:
    def __init__(self, connection: CybosConnection, account: str, goods_code: str):
        self._conn = connection
        self._account = account
        self._goods_code = goods_code

    def buy_limit(self, code: str, qty: int, price: int) -> dict:
        # Guard against stale COM proxy: confirm connection is alive.
        # If CYBOS was restarted/relogged, BlockRequest can hard-crash (access
        # violation) instead of returning an error. Bail out cleanly.
        if not self._conn.is_connected:
            raise RuntimeError("CYBOS not connected — buy order aborted")
        self._conn.wait_if_limited(1)
        obj = win32com.client.Dispatch("CpTrade.CpTd0311")
        obj.SetInputValue(0, "2")
        obj.SetInputValue(1, self._account)
        obj.SetInputValue(2, self._goods_code)
        obj.SetInputValue(3, code)
        obj.SetInputValue(4, qty)
        obj.SetInputValue(5, price)
        obj.SetInputValue(7, "0")
        obj.SetInputValue(8, "01")
        ret = obj.BlockRequest()
        if ret != 0:
            raise RuntimeError(f"Buy BlockRequest failed: ret={ret}")
        status = obj.GetDibStatus()
        msg = obj.GetDibMsg1()
        if status != 0:
            raise RuntimeError(f"Buy order failed: status={status} msg={msg}")
        order_num = obj.GetHeaderValue(8)
        log.info(f"Buy order placed: {code} {qty}@{price}, order_num={order_num}")
        return {"order_num": order_num}

    def sell_market(self, code: str, qty: int) -> dict:
        self._conn.wait_if_limited(1)
        obj = win32com.client.Dispatch("CpTrade.CpTd0311")
        obj.SetInputValue(0, "1")
        obj.SetInputValue(1, self._account)
        obj.SetInputValue(2, self._goods_code)
        obj.SetInputValue(3, code)
        obj.SetInputValue(4, qty)
        obj.SetInputValue(8, "03")
        ret = obj.BlockRequest()
        if ret != 0:
            raise RuntimeError(f"Sell BlockRequest failed: ret={ret}")
        status = obj.GetDibStatus()
        msg = obj.GetDibMsg1()
        if status != 0:
            raise RuntimeError(f"Sell order failed: status={status} msg={msg}")
        order_num = obj.GetHeaderValue(8)
        log.info(f"Sell order placed: {code} {qty}@market, order_num={order_num}")
        return {"order_num": order_num}

    def cancel(self, order_num: int, code: str, qty: int) -> dict:
        self._conn.wait_if_limited(1)
        obj = win32com.client.Dispatch("CpTrade.CpTd0314")
        obj.SetInputValue(0, "1")
        obj.SetInputValue(1, order_num)
        obj.SetInputValue(2, self._account)
        obj.SetInputValue(3, self._goods_code)
        obj.SetInputValue(4, code)
        obj.SetInputValue(5, qty)
        ret = obj.BlockRequest()
        if ret != 0:
            raise RuntimeError(f"Cancel BlockRequest failed: ret={ret}")
        status = obj.GetDibStatus()
        msg = obj.GetDibMsg1()
        log.info(f"Cancel order: {order_num}, status={status}, msg={msg}")
        return {"status": status, "msg": msg}
