#!/usr/bin/env python
"""Make the Drive owner's OAuth refresh token, once, so the bots create files in the owner's Drive
directly (no Apps Script relay).

    python scripts/google/oauth_token.py path/to/client_secret.json

Before: Google Cloud console of the service account's project
  1. APIs & Services > Library: Google Drive API enabled
  2. OAuth consent screen: External, add your Gmail as a test user, then "Publish app"
     (In production) - a token of an app left in Testing stops working after 7 days
  3. Credentials > Create credentials > OAuth client ID > Desktop app > Download JSON

A browser opens: sign in with the account that owns the Drive folders and allow access (an
unverified-app warning is expected: Advanced > Go to ...). The three values printed go into the
GitHub secrets GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REFRESH_TOKEN
and into the local .env.
"""
import json
import sys

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(argv[0], SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        print("No refresh token came back: remove the app's access at myaccount.google.com/permissions and run again")
        return 1
    client = json.load(open(argv[0], encoding="utf-8"))
    client = client.get("installed") or client.get("web") or {}
    print(f"GOOGLE_OAUTH_CLIENT_ID={client.get('client_id')}")
    print(f"GOOGLE_OAUTH_CLIENT_SECRET={client.get('client_secret')}")
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={creds.refresh_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
