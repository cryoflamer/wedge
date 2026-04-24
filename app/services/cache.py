from __future__ import annotations

from collections.abc import Hashable
from typing import Any

_CACHE: dict[Hashable, Any] = {}


def get(key: Hashable) -> Any:
    return _CACHE.get(key)


def set(key: Hashable, value: Any) -> Any:
    _CACHE[key] = value
    return value


def invalidate(key_prefix: Hashable | str | None = None) -> None:
    if key_prefix is None:
        _CACHE.clear()
        return

    if isinstance(key_prefix, str):
        for key in list(_CACHE.keys()):
            if isinstance(key, str) and key.startswith(key_prefix):
                _CACHE.pop(key, None)
        return

    _CACHE.pop(key_prefix, None)
