from __future__ import annotations
import json
from pydantic import BaseModel


class CybosConfig(BaseModel):
    exe_path: str


class TelegramListenerConfig(BaseModel):
    api_id: int
    api_hash: str
    phone: str
    session_name: str


class TelegramBotConfig(BaseModel):
    token: str
    chat_id: int


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class DbConfig(BaseModel):
    path: str = "data/systrader.db"


class LoggingConfig(BaseModel):
    dir: str = "logs"
    log_level: str = "INFO"


class AppSettings(BaseModel):
    cybos: CybosConfig
    telegram_listener: TelegramListenerConfig
    telegram_bot: TelegramBotConfig
    web: WebConfig = WebConfig()
    db: DbConfig = DbConfig()
    logging: LoggingConfig = LoggingConfig()


_KEY_MAP = {
    "Cybos": "cybos",
    "TelegramListener": "telegram_listener",
    "TelegramBot": "telegram_bot",
    "Web": "web",
    "Db": "db",
    "Logging": "logging",
}

_FIELD_MAP = {
    "ExePath": "exe_path",
    "ApiId": "api_id",
    "ApiHash": "api_hash",
    "Phone": "phone",
    "SessionName": "session_name",
    "Token": "token",
    "ChatId": "chat_id",
    "Host": "host",
    "Port": "port",
    "Path": "path",
    "Dir": "dir",
    "LogLevel": "log_level",
}


def _to_snake(d: dict) -> dict:
    return {_FIELD_MAP.get(k, k): v for k, v in d.items()}


def load_settings(path: str = "appsettings.json") -> AppSettings:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    converted = {}
    for key, value in raw.items():
        snake_key = _KEY_MAP.get(key, key.lower())
        if isinstance(value, dict):
            converted[snake_key] = _to_snake(value)
        else:
            converted[snake_key] = value
    return AppSettings(**converted)
