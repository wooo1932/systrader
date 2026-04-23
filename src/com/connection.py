from __future__ import annotations
import logging
import time
import win32com.client
import pythoncom

log = logging.getLogger(__name__)


class CybosConnection:
    def __init__(self):
        self._cybos = None
        self._last_redispatch_at = 0.0
        self._dispatch()

    def _dispatch(self) -> None:
        """(Re-)create the COM proxy. Called on init and after detected failures."""
        try:
            self._cybos = win32com.client.Dispatch("CpUtil.CpCybos")
            self._last_redispatch_at = time.time()
        except Exception as e:
            log.warning(f"CpCybos Dispatch failed: {e}")
            self._cybos = None

    @property
    def is_connected(self) -> bool:
        if self._cybos is None:
            self._dispatch()
            if self._cybos is None:
                return False
        try:
            connected = self._cybos.IsConnect == 1
        except Exception as e:
            # Stale proxy raised — redispatch and retry once.
            log.info(f"is_connected COM call failed, redispatching: {e}")
            self._dispatch()
            try:
                return self._cybos.IsConnect == 1 if self._cybos else False
            except Exception:
                return False
        # IsConnect can also return 0 silently on a stale proxy after CYBOS
        # was relaunched. Throttle-redispatch every 10s while disconnected to
        # auto-detect the user's re-login without a process restart.
        if not connected and time.time() - self._last_redispatch_at >= 10.0:
            self._dispatch()
            try:
                connected = self._cybos.IsConnect == 1 if self._cybos else False
            except Exception:
                return False
        return connected

    def remaining_count(self, limit_type: int) -> int:
        if self._cybos is None:
            return 0
        try:
            return self._cybos.GetLimitRemainCount(limit_type)
        except Exception:
            return 0

    def wait_if_limited(self, limit_type: int) -> None:
        while self.remaining_count(limit_type) <= 0:
            log.debug(f"API rate limited (type={limit_type}), waiting...")
            pythoncom.PumpWaitingMessages()
            time.sleep(0.2)

    def get_server_type(self) -> str:
        if self._cybos is None:
            return ""
        try:
            return "simulated" if self._cybos.ServerType == 1 else "real"
        except Exception:
            return ""
