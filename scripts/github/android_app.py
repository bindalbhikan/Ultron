"""Ultron Phone builds on GitHub (.github/workflows/android-app.yml), kept in Drive AGENT WORK/ULTRON PHONE.

    python scripts/github/android_app.py keystore <dir>   the signing key from Drive (made on the first
                                                          build), its path and password into $GITHUB_ENV
    python scripts/github/android_app.py upload <apk>     the APK to Drive as "Ultron Phone.apk" (updated
                                                          in place) and a Telegram note with the link

One fixed key, so every new APK installs over the one on the phone. It lives only in the owner's Drive
(never in this public repo); losing it means uninstalling the app once before the next install.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ultron.workings.core.config import env  # noqa: E402
from ultron.workings.core.drive import DriveFolder  # noqa: E402

AGENT_WORK = "1uO-aOha_QKkI3f19EA7sweYPgkjMukZI"   # Drive BINDAL EXPORTS/AGENT WORK
FOLDER = "ULTRON PHONE"
KEYSTORE, PASSWORD, APK = "ultronphone.keystore", "ultronphone.keystore.password", "Ultron Phone.apk"


def folder() -> DriveFolder:
    return DriveFolder(env("AGENT_WORK_FOLDER_ID", AGENT_WORK)).subfolder(FOLDER, create=True)


def keystore(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    f = folder()
    ks, pw = out / KEYSTORE, out / PASSWORD
    if f.download(KEYSTORE, ks) and f.download(PASSWORD, pw):
        print("signing key: from Drive")
    else:
        pw.write_text(secrets.token_urlsafe(24), encoding="utf-8")
        subprocess.run(["keytool", "-genkeypair", "-keystore", str(ks), "-storetype", "PKCS12", "-alias", "ultronphone",
                        "-keyalg", "RSA", "-keysize", "2048", "-validity", "18250", "-storepass", pw.read_text(),
                        "-dname", "CN=Ultron Phone, O=Bindal Exports, C=IN"], check=True, capture_output=True)
        f.put(ks, "application/octet-stream")
        f.put(pw, "text/plain")
        print("signing key: new, saved to Drive AGENT WORK/ULTRON PHONE")
    password = pw.read_text(encoding="utf-8").strip()
    print(f"::add-mask::{password}")
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as g:
        g.write(f"ANDROID_KEYSTORE_FILE={ks}\nANDROID_KEYSTORE_PASSWORD={password}\n")


def upload(apk: Path) -> None:
    named = apk.with_name(APK)
    named.write_bytes(apk.read_bytes())
    file_id = folder().put(named, "application/vnd.android.package-archive")
    link = f"https://drive.google.com/file/d/{file_id}/view"
    version = env("APP_VERSION_CODE", "?")
    print(f"APK saved: AGENT WORK/{FOLDER}/{APK} ({link})")
    if env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"):
        from ultron.workings.core import telegram
        telegram.send(f"📱 <b>Ultron Phone v2.0.{version} built</b>\n<i>AGENT WORK/{FOLDER}</i>\n\n"
                      f"Open on the phone and install over the old one:\n{link}")


if __name__ == "__main__":
    cmd, arg = sys.argv[1], Path(sys.argv[2])
    keystore(arg) if cmd == "keystore" else upload(arg)
