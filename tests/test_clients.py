"""workings/core/clients.py: every working's portal login in one place (docs/CENTRALISE.md step 1)."""
import pytest

from ultron.workings.core import clients


def test_missing_login_names_the_secrets(monkeypatch):
    monkeypatch.delenv("AJIO_USERNAME", raising=False)
    monkeypatch.setenv("AJIO_PASSWORD", "x")
    with pytest.raises(clients.MissingLogin, match="AJIO_USERNAME / AJIO_PASSWORD not set"):
        clients.ajio()
    assert issubclass(clients.MissingLogin, RuntimeError)      # callers catching RuntimeError still do


def test_flipkart_and_srm_log_in(monkeypatch):
    from ultron.workings.portals import flipkart, srm
    seen = []

    class Fake:
        def __init__(self, user, pwd):
            seen.append((type(self).__name__, user, pwd))

        def login(self):
            seen.append("login")
    monkeypatch.setattr(flipkart, "FlipkartClient", type("FlipkartClient", (Fake,), {}))
    monkeypatch.setattr(srm, "Srm", type("Srm", (Fake,), {}))
    for k, v in {"FLIPKART_EMAIL": "e", "FLIPKART_PASSWORD": "p", "SRM_USERNAME": "u", "SRM_PASSWORD": "q"}.items():
        monkeypatch.setenv(k, v)
    clients.flipkart()
    clients.srm()
    assert seen == [("FlipkartClient", "e", "p"), "login", ("Srm", "u", "q"), "login"]


def test_omsguru_chooses_the_first_warehouse_when_asked(monkeypatch):
    from ultron.portals import omsguru
    calls = []

    class Fake:
        @classmethod
        def from_env(cls):
            return cls()

        def login(self):
            calls.append("login")

        def warehouses(self):
            return {"11": "A", "22": "B"}

        def set_warehouse(self, wh):
            calls.append(("warehouse", wh))
    monkeypatch.setattr(omsguru, "OmsGuruClient", Fake)
    clients.omsguru()
    clients.omsguru(warehouse=True)
    assert calls == ["login", "login", ("warehouse", "11")]


def test_return_analysis_helpers_go_through_clients(monkeypatch):
    from ultron.workings.return_analysis import sources
    monkeypatch.setattr(clients, "myntra", lambda account: f"portal {account}")
    monkeypatch.setattr(clients, "flipkart", lambda: "fk")
    assert sources.myntra_portal("DBCC") == "portal DBCC" and sources.flipkart_client() == "fk"
