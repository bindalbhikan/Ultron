"""Logged-in portal clients, made in one place (docs/CENTRALISE.md, step 1).

Every working used to repeat "read the login from the secrets, say which one is missing, build the
client, log in" (OMSGuru in ~17 places, AJIO in 6, two different Myntra helpers). Use these instead:

    omsguru(warehouse=True)   OMSGuru, logged in (and the first warehouse chosen when asked)
    ajio()                    AJIO seller portal (AJIO_USERNAME / AJIO_PASSWORD)
    srm()                     AJIO SRM, the ledger (SRM_USERNAME / SRM_PASSWORD)
    flipkart()                Flipkart Seller Hub (FLIPKART_EMAIL / FLIPKART_PASSWORD)
    myntra(account)           Myntra partner portal, saved session of MAIN / DBCC / FMCC, checked
    myntra_done(portal, account)   save the cookies the portal renewed (call when finished)

A missing login raises MissingLogin naming the secrets, before any portal is asked.
"""
from __future__ import annotations

from .config import env


class MissingLogin(RuntimeError):
    """A portal's login is not in the secrets / .env."""


def _login(*names: str) -> list[str]:
    values = [env(n) for n in names]
    if not all(values):
        raise MissingLogin(" / ".join(names) + " not set")
    return values


def omsguru(warehouse: bool = False):
    from ultron.portals.omsguru import OmsGuruClient
    client = OmsGuruClient.from_env()
    client.login()
    if warehouse:
        client.set_warehouse(next(iter(client.warehouses())))
    return client


def ajio():
    from ..portals.ajio import AjioClient
    client = AjioClient(*_login("AJIO_USERNAME", "AJIO_PASSWORD"))
    client.login()
    return client


def srm():
    from ..portals.srm import Srm
    client = Srm(*_login("SRM_USERNAME", "SRM_PASSWORD"))
    client.login()
    return client


def flipkart():
    from ..portals.flipkart import FlipkartClient
    client = FlipkartClient(*_login("FLIPKART_EMAIL", "FLIPKART_PASSWORD"))
    client.login()
    return client


def myntra(account: str = "MAIN"):
    """The account's partner portal from its session saved on the worker; SessionExpired when there
    is none or it no longer works."""
    from ..portals import myntra as mp
    text = mp.from_worker(env, account)
    if not text:
        raise mp.SessionExpired(f"no {account} session saved (python scripts/myntra/myntra_session.py {account})")
    portal = mp.MyntraPortal(mp.parse_session(text))
    portal.check()
    return portal


def myntra_done(portal, account: str = "MAIN") -> bool:
    """Save the cookies the portal renewed, so the session stays alive for the next run."""
    from ..portals import myntra as mp
    return mp.save_to_worker(env, portal.cookies(), account)
