"""A bot's settings checked at its start (docs/libraries/10-small.md, pydantic-settings).

    check_settings("ultron.workings.sale.pipeline")    stop now, naming the setting, when a number or yes / no
                                                         setting holds something else; warn of required ones missing

The settings a bot reads are found in its own code: every num / flag / required call (name in quotes) in its
package folder and in workings/core. They become one typed pydantic-settings model read from the environment and
the project's .env (a blank value is unset, as GitHub passes an unset variable). Before, a typo such as
SALE_REPORT_DAYS=l (an L) quietly fell back to the default and the run went on with other numbers than meant.

A missing required setting is only named in the log here: some are read on one path of a bot alone, and
required() itself still stops the run, naming it, when that path is reached.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path
from typing import Annotated

from .config import FALSE, ROOT, TRUE

log = logging.getLogger("bindal.settings")
CALL = re.compile(r'\b(num|flag|required)\(\s*"([A-Z][A-Z0-9_]*)"')
CORE = Path(__file__).resolve().parent


def _whole_number(value: str) -> str:
    int(value.strip())          # the same reading as config.num(); ValueError names the value
    return value


def _yes_no(value: str) -> str:
    if value.strip().lower() not in TRUE + FALSE:
        raise ValueError(f"not one of {', '.join(TRUE + FALSE)}")
    return value


def _folders(module: str) -> list[Path]:
    spec = find_spec(module)
    origin = Path(spec.origin).resolve() if spec and spec.origin else None
    return [p for p in (origin.parent if origin else None, CORE) if p]


@lru_cache(maxsize=None)
def used_settings(module: str) -> dict[str, str]:
    """name -> num / flag / required, for the settings the module's package and workings/core read."""
    out: dict[str, str] = {}
    for folder in _folders(module):
        for f in sorted(folder.glob("*.py")):
            for kind, name in CALL.findall(f.read_text(encoding="utf-8", errors="replace")):
                if folder == CORE and kind == "required":
                    continue        # the shared helpers' required ones belong to the bots that call them
                out.setdefault(name, kind)
    return out


def model_for(names: dict[str, str]):
    """A pydantic-settings model with one optional field per setting, typed by how the bots read it."""
    from pydantic import AfterValidator, create_model
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Base(BaseSettings):
        model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), env_file_encoding="utf-8", env_ignore_empty=True,
                                          extra="ignore", case_sensitive=True)

    kinds = {"num": Annotated[str, AfterValidator(_whole_number)], "flag": Annotated[str, AfterValidator(_yes_no)],
             "required": str}
    fields = {name: (kinds[kind] | None, None) for name, kind in names.items()}
    return create_model("BotSettings", __base__=Base, **fields)  # type: ignore[call-overload]


def check_settings(module: str) -> None:
    """Stop now (RuntimeError naming each one) when a number or yes / no setting holds something else; log the
    required settings that are missing."""
    from pydantic import ValidationError
    names = used_settings(module)
    if not names:
        return
    try:
        got = model_for(names)()
    except ValidationError as exc:
        bad = "; ".join(f"{e['loc'][0]}={e.get('input')!r} ({e['msg'].removeprefix('Value error, ')})" for e in exc.errors())
        raise RuntimeError(f"Settings in another shape than the bot reads: {bad}") from None
    missing = sorted(n for n, k in names.items() if k == "required" and getattr(got, n) is None)
    if missing:
        log.warning("Settings missing (the run stops if it reaches them): %s", ", ".join(missing))
