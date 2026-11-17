"""A bot's settings checked at its start (pydantic-settings, docs/libraries/10-small.md)."""
import pytest

from ultron.workings.core import settings


def test_found_in_the_bots_code():
    names = settings.used_settings("ultron.workings.sale.pipeline")
    assert names["SALE_REPORT_DAYS"] == "num" and "X" not in names


def test_wrong_shapes_stop_the_run_named(monkeypatch):
    monkeypatch.setattr(settings, "used_settings", lambda m: {"DAYS": "num", "ON": "flag", "SHEET": "required"})
    monkeypatch.setenv("DAYS", "l0")
    monkeypatch.setenv("ON", "maybe")
    with pytest.raises(RuntimeError) as e:
        settings.check_settings("x")
    assert "DAYS='l0'" in str(e.value) and "ON='maybe'" in str(e.value)


def test_good_blank_and_missing(monkeypatch, caplog):
    monkeypatch.setattr(settings, "used_settings", lambda m: {"DAYS": "num", "ON": "flag", "SHEET": "required"})
    monkeypatch.setenv("DAYS", " 7 ")
    monkeypatch.setenv("ON", "")              # GitHub's unset variable: blank = unset, no error
    monkeypatch.delenv("SHEET", raising=False)
    settings.check_settings("x")
    assert "SHEET" in caplog.text            # named, the run goes on
