"""Bindal's own Ultron tools (agent.toml [chat] / [watch] tools): read-only checks on the logins
the workings use."""
from __future__ import annotations

from ultron.core.llm import tool

from .core.config import env
from .portals import myntra


@tool
def myntra_login_status() -> str:
    """Whether the Myntra partner-portal logins saved on the worker (accounts MAIN, DBCC, FMCC) still
    work: logged in or out, which seller account each is for, when it was saved and when its cookies
    run out. Read-only: it only asks the portal one question per account."""
    lines = []
    for account, partner in myntra.ACCOUNTS.items():
        text = myntra.from_worker(env, account)
        if not text:
            lines.append(f"{account}: no login saved on the worker")
            continue
        try:
            session = myntra.parse_session(text)
            portal = myntra.MyntraPortal(session)
            portal.check()
            got = portal.partner_id()
        except myntra.SessionExpired as exc:
            lines.append(f"{account}: LOGGED OUT ({exc})")
            continue
        except Exception as exc:  # noqa: BLE001 - the model reads it
            lines.append(f"{account}: could not check ({type(exc).__name__}: {str(exc)[:150]})")
            continue
        ends, saved = session.expires(), session.saved_at
        who = "the right account" if got == partner else f"partner {got}, expected {partner}"
        lines.append(f"{account}: logged in ({who})"
                     + (f", saved {saved:%d %b %Y %H:%M}" if saved else "")
                     + (f", cookies run out {ends:%d %b %Y %H:%M}" if ends else ", cookie expiry unknown"))
    lines.append("A logged-out account needs a new login: python scripts/myntra/myntra_session.py on the owner's PC.")
    return "\n".join(lines)


TOOLS = [myntra_login_status]
