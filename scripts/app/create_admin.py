"""Make (or promote) an administrator of the ULTRON app, from the owner's own terminal.

    cd D:\\ULTRON
    .venv\\Scripts\\python scripts\\app\\create_admin.py

It asks for the name, username and password (the password is typed hidden, twice, and goes only to the app
API, never to a file or a log), registers the account through the live API, then makes it an active
administrator in the D1 database with wrangler (which must be logged in to the Cloudflare account).
An existing username is only promoted; its password is left as it is.
"""
from __future__ import annotations

import getpass
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://ultron-app-api.bhikan-serein.workers.dev"
APP_API = Path(__file__).resolve().parents[2] / "services" / "app_api"
USERNAME = re.compile(r"^[A-Za-z0-9_.]{3,30}$")


def register(name: str, username: str, password: str) -> str:
    body = json.dumps({"name": name, "username": username, "password": password}).encode()
    req = urllib.request.Request(f"{API}/api/auth/sign-up/email", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return f"registered ({r.status})"
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")[:200]
        if "exist" in text.lower() or e.code == 422:
            return "already registered: only promoted"
        sys.exit(f"Registration refused: HTTP {e.code} {text}")


def promote(username: str) -> None:
    sql = ("UPDATE app_access SET status='active', role_id='admin', revision=revision+1, "
           "updated_at=unixepoch()*1000 WHERE user_id=(SELECT id FROM user WHERE username='" + username.lower() + "')")
    run = subprocess.run(["npx", "--no-install", "wrangler", "d1", "execute", "ultron", "--remote", "--json",
                          "--command", sql], cwd=APP_API, capture_output=True, text=True, shell=sys.platform == "win32")
    if run.returncode != 0:
        sys.exit("wrangler failed (is it logged in? cd services/app_api && npx wrangler login):\n" + run.stderr[-500:])
    changes = sum(r.get("meta", {}).get("changes", 0) for r in json.loads(run.stdout))
    if changes < 1:
        sys.exit(f"No account with the username {username!r} was found.")


def main() -> None:
    name = input("Full name: ").strip()
    username = input("Username: ").strip()
    if len(name) < 2 or not USERNAME.match(username):
        sys.exit("A name of 2+ characters and a username of 3-30 letters, digits, dots or underscores.")
    password = getpass.getpass("Password (10+ characters, hidden): ")
    if len(password) < 10 or password != getpass.getpass("Password again: "):
        sys.exit("The passwords differ or are shorter than 10 characters.")
    print(register(name, username, password))
    promote(username)
    print(f"{username} is now an active administrator. Sign in to the ULTRON app with this username.")


if __name__ == "__main__":
    main()
