import sys
import time
from unittest.mock import MagicMock, patch
import pytest
from src.core.event_bus import EventBus

# Mock win32com before importing cybos_news
sys.modules.setdefault("win32com", MagicMock())
sys.modules.setdefault("win32com.client", MagicMock())

# Mock telethon before importing telegram_news
sys.modules.setdefault("telethon", MagicMock())
sys.modules.setdefault("telethon.events", MagicMock())

from src.news.cybos_news import CybosNewsSource, CybosNewsHandler
from src.news.telegram_news import TelegramNewsSource


# ---------- helpers ----------

def make_code_manager(stocks=None):
    cm = MagicMock()
    stocks = stocks or [("삼성전자", "A005930"), ("카카오", "A035720")]
    cm.code_to_name = lambda c: dict((code, name) for name, code in stocks).get(c, "")
    cm.all_stocks = lambda: stocks
    return cm


# ---------- CybosNewsSource ----------

class TestCybosNewsSource:
    def test_on_news_publishes_news_feed(self):
        bus = EventBus()
        cm = make_code_manager()
        source = CybosNewsSource(bus, cm)
        received = []
        bus.subscribe("news_feed", lambda d: received.append(d))

        source._on_news("A005930", "삼성전자 실적 발표")

        assert len(received) == 1
        assert received[0]["stock_code"] == "A005930"
        assert received[0]["stock_name"] == "삼성전자"
        assert received[0]["source"] == "cybos"
        assert received[0]["text"] == "삼성전자 실적 발표"

    def test_on_news_publishes_news_detected_for_keyword(self):
        bus = EventBus()
        cm = make_code_manager()
        source = CybosNewsSource(bus, cm)
        detected = []
        bus.subscribe("news_detected", lambda d: detected.append(d))

        source._on_news("A005930", "삼성전자 단일판매 공시")

        assert len(detected) == 1
        assert detected[0]["code"] == "A005930"
        assert detected[0]["name"] == "삼성전자"
        assert detected[0]["source"] == "cybos"

    def test_on_news_no_detected_without_keyword(self):
        bus = EventBus()
        cm = make_code_manager()
        source = CybosNewsSource(bus, cm)
        detected = []
        bus.subscribe("news_detected", lambda d: detected.append(d))

        source._on_news("A005930", "삼성전자 실적 발표")

        assert len(detected) == 0

    def test_on_news_no_detected_when_code_empty(self):
        bus = EventBus()
        cm = make_code_manager()
        source = CybosNewsSource(bus, cm)
        detected = []
        bus.subscribe("news_detected", lambda d: detected.append(d))

        source._on_news("", "시장 전체 뉴스")

        assert len(detected) == 0

    def test_on_news_no_detected_when_name_not_found(self):
        bus = EventBus()
        cm = MagicMock()
        cm.code_to_name = lambda c: ""
        source = CybosNewsSource(bus, cm)
        detected = []
        bus.subscribe("news_detected", lambda d: detected.append(d))

        source._on_news("A999999", "알 수 없는 종목")

        assert len(detected) == 0

    def test_on_news_timestamp_format(self):
        bus = EventBus()
        cm = make_code_manager()
        source = CybosNewsSource(bus, cm)
        received = []
        bus.subscribe("news_feed", lambda d: received.append(d))

        source._on_news("A005930", "test")

        ts = received[0]["timestamp"]
        assert len(ts) == 19  # YYYY-MM-DDTHH:MM:SS
        assert "T" in ts

    @patch("src.news.cybos_news.win32com.client.DispatchWithEvents")
    def test_start_subscribes(self, mock_dispatch):
        bus = EventBus()
        cm = make_code_manager()
        mock_obj = MagicMock()
        mock_dispatch.return_value = mock_obj

        source = CybosNewsSource(bus, cm)
        source.start()

        mock_dispatch.assert_called_once_with("Dscbo1.CpSvr8092S", CybosNewsHandler)
        mock_obj.Subscribe.assert_called_once()

    @patch("src.news.cybos_news.win32com.client.DispatchWithEvents")
    def test_stop_unsubscribes(self, mock_dispatch):
        bus = EventBus()
        cm = make_code_manager()
        mock_obj = MagicMock()
        mock_dispatch.return_value = mock_obj

        source = CybosNewsSource(bus, cm)
        source.start()
        source.stop()

        mock_obj.Unsubscribe.assert_called_once()

    def test_stop_without_start_is_safe(self):
        bus = EventBus()
        cm = make_code_manager()
        source = CybosNewsSource(bus, cm)
        source.stop()  # should not raise


# ---------- TelegramNewsSource ----------

class TestTelegramNewsSource:
    def _make_source(self, bus=None, cm=None):
        bus = bus or EventBus()
        cm = cm or make_code_manager()
        return TelegramNewsSource(
            api_id=12345, api_hash="testhash", phone="+821012345678",
            session_name="test_session", event_bus=bus, code_manager=cm,
        )

    def test_on_message_publishes_news_feed(self):
        bus = EventBus()
        source = self._make_source(bus=bus)
        received = []
        bus.subscribe("news_feed", lambda d: received.append(d))

        source._on_message("테스트 메시지", "테스트채널")

        assert len(received) == 1
        assert received[0]["source"] == "telegram"
        assert received[0]["category"] == "테스트채널"
        assert received[0]["text"] == "테스트 메시지"

    def test_on_message_detects_stock_names(self):
        bus = EventBus()
        cm = make_code_manager()
        source = self._make_source(bus=bus, cm=cm)
        detected = []
        bus.subscribe("news_detected", lambda d: detected.append(d))

        source._on_message("삼성전자 신규 투자 발표", "뉴스채널")

        assert len(detected) == 1
        assert detected[0]["code"] == "A005930"
        assert detected[0]["name"] == "삼성전자"
        assert detected[0]["source"] == "telegram"

    def test_on_message_detects_multiple_stocks(self):
        bus = EventBus()
        cm = make_code_manager()
        source = self._make_source(bus=bus, cm=cm)
        detected = []
        bus.subscribe("news_detected", lambda d: detected.append(d))

        source._on_message("삼성전자와 카카오 동반 상승", "뉴스채널")

        assert len(detected) == 2
        codes = {d["code"] for d in detected}
        assert codes == {"A005930", "A035720"}

    def test_on_message_no_detection_when_no_match(self):
        bus = EventBus()
        cm = make_code_manager()
        source = self._make_source(bus=bus, cm=cm)
        detected = []
        bus.subscribe("news_detected", lambda d: detected.append(d))

        source._on_message("오늘 날씨가 좋습니다", "일반채널")

        assert len(detected) == 0

    def test_extract_stocks_ignores_single_char_names(self):
        cm = MagicMock()
        cm.all_stocks = lambda: [("A", "A000001"), ("삼성전자", "A005930")]
        source = self._make_source(cm=cm)

        results = source._extract_stocks("A와 삼성전자")

        assert len(results) == 1
        assert results[0] == ("A005930", "삼성전자")

    def test_extract_stocks_no_duplicate_codes(self):
        cm = make_code_manager()
        source = self._make_source(cm=cm)

        results = source._extract_stocks("삼성전자 삼성전자 삼성전자")

        assert len(results) == 1

    def test_set_channels(self):
        source = self._make_source()
        source.set_channels(["ch1", "ch2"])
        assert source._channels == ["ch1", "ch2"]

    def test_on_message_title_truncated_to_100(self):
        bus = EventBus()
        cm = make_code_manager()
        source = self._make_source(bus=bus, cm=cm)
        detected = []
        bus.subscribe("news_detected", lambda d: detected.append(d))

        long_text = "삼성전자 " + "x" * 200
        source._on_message(long_text, "뉴스채널")

        assert len(detected[0]["title"]) == 100
