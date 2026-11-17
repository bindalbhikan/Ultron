"""JSON read fast (docs/libraries/10-small.md): orjson (Rust) when installed, else the json module.

    loads(data)     str or bytes -> Python; the same objects either way

orjson is 5-10x faster on big answers (Myntra report jobs, SPF tickets, Flipkart / AJIO lists). It is not pure Python,
so the seller-neutral core (Android / Termux) falls back to json. Two cases go to json on purpose:
  * text orjson refuses (NaN, Infinity): json reads it, so nothing that read before fails now;
  * a number of 20 digits or more: orjson reads one beyond 64 bits as a float (1e+30), json keeps it exact. A long id
    must never come back rounded ("data must never be wrong"), so such text is read by json whole.
"""
from __future__ import annotations

import json
from typing import Any

try:
    import orjson as _orjson
except ImportError:                        # pragma: no cover - Termux: pure Python
    _orjson = None

# a run of 20 digits, found in one C pass: every digit made "0", everything else a space
_DIGITS = bytes(48 if 48 <= c <= 57 else 32 for c in range(256))
_TWENTY = b"0" * 20


def loads(data: str | bytes | bytearray) -> Any:
    if _orjson is not None:
        raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if _TWENTY not in raw.translate(_DIGITS):
            try:
                return _orjson.loads(raw)
            except _orjson.JSONDecodeError:
                pass                        # json says why, or reads what orjson will not (NaN, Infinity)
    return json.loads(data)
