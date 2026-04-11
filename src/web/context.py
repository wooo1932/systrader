from __future__ import annotations

_app_context: dict = {}


def get_context() -> dict:
    return _app_context
