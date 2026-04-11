import json
import os
import tempfile
import pytest
from src.config import load_settings, AppSettings


def _write_config(path, overrides=None):
    base = {
        "Cybos": {"ExePath": "C:\\DAISHIN\\STARTER\\ncStarter.exe"},
        "TelegramListener": {
            "ApiId": 123, "ApiHash": "abc", "Phone": "+8210", "SessionName": "test"
        },
        "TelegramBot": {"Token": "tok", "ChatId": 999},
        "Web": {"Host": "0.0.0.0", "Port": 8000},
        "Db": {"Path": "data/test.db"},
        "Logging": {"Dir": "logs", "LogLevel": "INFO"},
    }
    if overrides:
        base.update(overrides)
    with open(path, "w") as f:
        json.dump(base, f)


def test_load_settings_parses_all_sections(tmp_path):
    cfg_path = tmp_path / "appsettings.json"
    _write_config(str(cfg_path))
    settings = load_settings(str(cfg_path))
    assert isinstance(settings, AppSettings)
    assert settings.cybos.exe_path == "C:\\DAISHIN\\STARTER\\ncStarter.exe"
    assert settings.telegram_listener.api_id == 123
    assert settings.telegram_bot.chat_id == 999
    assert settings.web.port == 8000
    assert settings.db.path == "data/test.db"
    assert settings.logging.log_level == "INFO"


def test_load_settings_defaults(tmp_path):
    cfg_path = tmp_path / "appsettings.json"
    minimal = {
        "Cybos": {"ExePath": "c:\\test.exe"},
        "TelegramListener": {
            "ApiId": 1, "ApiHash": "x", "Phone": "+1", "SessionName": "s"
        },
        "TelegramBot": {"Token": "t", "ChatId": 1},
        "Db": {"Path": "data/test.db"},
        "Logging": {"Dir": "logs", "LogLevel": "DEBUG"},
    }
    with open(str(cfg_path), "w") as f:
        json.dump(minimal, f)
    settings = load_settings(str(cfg_path))
    assert settings.web.host == "0.0.0.0"
    assert settings.web.port == 8000
