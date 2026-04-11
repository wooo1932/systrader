import pytest
import json
import os
from fastapi.testclient import TestClient
from src.database import Database
from src.core.event_bus import EventBus
from src.core.command_queue import CommandQueue
from src.web.server import app
from src.web.context import _app_context


@pytest.fixture
def client(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.ensure_schema()
    _app_context.clear()
    _app_context.update({
        "db": db,
        "event_bus": EventBus(),
        "command_queue": CommandQueue(),
        "connection": None,
        "account": None,
        "engine": None,
        "telegram_news": None,
        "settings_path": str(tmp_path / "settings.json"),
        "log_dir": str(tmp_path / "logs"),
    })
    with open(str(tmp_path / "settings.json"), "w") as f:
        json.dump({"Web": {"Port": 8000}}, f)
    os.makedirs(str(tmp_path / "logs"), exist_ok=True)
    return TestClient(app)


def test_get_trades_empty(client):
    resp = client.get("/api/trades")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_params_empty(client):
    resp = client.get("/api/settings/params")
    assert resp.status_code == 200
    assert resp.json() == []


def test_update_and_get_param(client):
    client.put("/api/settings/params/max_holdings", json={"value": "5"})
    resp = client.get("/api/settings/params")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["key"] == "max_holdings"
    assert data[0]["value"] == "5"


def test_channels_crud(client):
    client.post("/api/settings/channels", json={
        "channel_url": "https://t.me/test", "channel_name": "Test"
    })
    resp = client.get("/api/settings/channels")
    assert len(resp.json()) == 1

    client.put("/api/settings/channels/1/toggle")
    resp = client.get("/api/settings/channels")
    assert resp.json()[0]["enabled"] == 0

    client.delete("/api/settings/channels/1")
    resp = client.get("/api/settings/channels")
    assert resp.json() == []


def test_get_status_without_cybos(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cybos_connected"] is False


def test_news_feed(client):
    resp = client.get("/api/news-feed")
    assert resp.status_code == 200


def test_logs_live(client):
    resp = client.get("/api/logs/live?after=0")
    assert resp.status_code == 200
    assert "logs" in resp.json()
