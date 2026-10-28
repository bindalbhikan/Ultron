"""Google credentials, shared by the Sheets and Drive modules: the service account, and for Drive
the owner's OAuth refresh token when it is set.

GitHub Actions: the whole key JSON in GOOGLE_SERVICE_ACCOUNT_JSON.
Local runs: the key file at GOOGLE_SERVICE_ACCOUNT_FILE (relative paths are
taken from the project folder, default service_account.json).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from google.oauth2.service_account import Credentials

from .config import ROOT


def oauth_configured() -> bool:
    """GOOGLE_OAUTH_CLIENT_ID / _SECRET / _REFRESH_TOKEN set: Drive is used as the owner's account
    (scripts/google/oauth_token.py makes the token)."""
    return all(os.getenv(k, "").strip() for k in
               ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN"))


def drive_credentials(scopes: list[str]):
    """The Drive owner's own account when OAuth is set (it can create files: a service account
    has no storage of its own in a personal Drive), else the service account."""
    if not oauth_configured():
        return credentials(scopes)
    from google.oauth2.credentials import Credentials as UserCredentials
    return UserCredentials(None, refresh_token=os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"].strip(),
                           token_uri="https://oauth2.googleapis.com/token", scopes=scopes,
                           client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"].strip(),
                           client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"].strip())


def credentials(scopes: list[str]) -> Credentials:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        return Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
    path = Path(os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip() or "service_account.json")
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise RuntimeError("Google credentials missing: set GOOGLE_SERVICE_ACCOUNT_JSON "
                           f"or put the key file at {path}")
    return Credentials.from_service_account_file(str(path), scopes=scopes)
