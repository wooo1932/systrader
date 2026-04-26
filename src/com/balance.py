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
        """Return broker holdings from CpTd6033. Uses CYBOS-provided fields directly
        (no local computation) for accuracy:
          - avg_price (int, field 4): 매수평단가
          - quantity  (int, field 7): 체결잔고수량
          - eval_amount (field 9): 평가금액
          - pnl_amount  (field 10): 평가손익
          - pnl_pct     (field 11): 손익률 (%)
        Retries up to 3x on transient errors (ret=1 comm drop, ret=4 rate limit).
        """
        import time as _t
        obj = None
        ret = -1
        for attempt in range(3):
            self._conn.wait_if_limited(1)
            obj = win32com.client.Dispatch("CpTrade.CpTd6033")
            obj.SetInputValue(0, self._account)
            obj.SetInputValue(1, self._goods_code)
            obj.SetInputValue(2, 50)
            ret = obj.BlockRequest()
            if ret == 0:
                break
            # Transient errors worth retrying:
            #   ret=1 → comm connection dropped briefly
            #   ret=4 → trade API rate limit (20 req/s)
            if ret in (1, 4):
                log.debug(f"CpTd6033 transient ret={ret}, attempt {attempt+1}/3, backing off")
                _t.sleep(0.3 * (attempt + 1))
                continue
            log.warning(f"CpTd6033 BlockRequest failed: ret={ret}")
            return []
        if ret != 0:
            log.warning(f"CpTd6033 still failing (ret={ret}) after 3 attempts; skipping this cycle")
            return []
        if obj.GetDibStatus() != 0:
            log.warning(f"CpTd6033 error: {obj.GetDibMsg1()}")
            return []
        count = obj.GetHeaderValue(7)
        holdings = []
        for i in range(count):
            try:
                holdings.append({
                    "code": obj.GetDataValue(12, i),
                    "name": obj.GetDataValue(0, i),
                    "quantity": int(obj.GetDataValue(7, i) or 0),
                    "avg_price": int(obj.GetDataValue(4, i) or 0),
                    "eval_amount": int(obj.GetDataValue(9, i) or 0),
                    "pnl_amount": int(obj.GetDataValue(10, i) or 0),
                    "pnl_pct": float(obj.GetDataValue(11, i) or 0),
                    # Keep legacy 'price' key for back-compat (= avg_price)
                    "price": int(obj.GetDataValue(4, i) or 0),
                })
            except Exception as e:
                log.warning(f"CpTd6033 row {i} parse error: {e}")
        return holdings
