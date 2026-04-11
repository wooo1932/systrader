from __future__ import annotations
import logging
import win32com.client

log = logging.getLogger(__name__)


class CodeManager:
    def __init__(self):
        self._stock_code = win32com.client.Dispatch("CpUtil.CpStockCode")
        self._code_mgr = win32com.client.Dispatch("CpUtil.CpCodeMgr")
        self._name_to_code: dict[str, str] = {}
        self._code_to_name: dict[str, str] = {}

    def load_stock_list(self) -> None:
        count = 0
        for market in (1, 2):
            codes = self._code_mgr.GetStockListByMarket(market)
            for code in codes:
                name = self._code_mgr.CodeToName(code)
                self._name_to_code[name] = code
                self._code_to_name[code] = name
                count += 1
        log.info(f"Loaded {count} stock codes")

    def name_to_code(self, name: str) -> str | None:
        return self._name_to_code.get(name)

    def code_to_name(self, code: str) -> str | None:
        return self._code_to_name.get(code)

    def all_stocks(self) -> list[tuple[str, str]]:
        return list(self._name_to_code.items())

    def get_section_kind(self, code: str) -> int:
        return self._code_mgr.GetStockSectionKind(code)
