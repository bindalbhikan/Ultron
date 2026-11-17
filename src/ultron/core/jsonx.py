"""JSON read fast (docs/libraries/10-small.md): orjson (Rust) when installed, else the json module.

    loads(data)     str or bytes -> Python; the same objects either way

orjson is 5-10x faster on big answers (Myntra report jobs, SPF tickets, Flipkart / AJIO lists). It is not pure Python,
so the seller-neutral core (Android / Termux) falls back to json. Text orjson refuses but json reads (NaN, a number
beyond 64 bits) is read by json, so nothing that read before fails now.
"""
from __future__ import annotations

import json
from typing import Any

try:
    import orjson as _orjson
except ImportError:                        # pragma: no cover - Termux: pure Python
    _orjson = None


def loads(data: str | bytes | bytearray) -> Any:
    if _orjson is not None:
        try:
            return _orjson.loads(data)
        except _orjson.JSONDecodeError:
            pass                            # json says why, or reads what orjson will not (NaN, huge numbers)
    return json.loads(data)
