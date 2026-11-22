"""The Android signing key of the ULTRON app's APK (.github/workflows/flutter-app.yml), kept in Drive.

    python scripts/github/android_app.py keystore <dir>   the key from Drive AGENT WORK/ULTRON PHONE (made on the
                                                          first build), its path and password into $GITHUB_ENV

One fixed key, so every new APK installs over the one on the phone. It lives only in the owner's Drive (never
in this public repo); losing it means uninstalling the app once before the next install. The key is the one
the old Ultron Phone app used (its folder and alias kept), so phones keep their trust in it.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path
from ultron.workings.core.config import agent_work_id

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ultron.workings.core.drive import DriveFolder  # noqa: E402

FOLDER = "ULTRON PHONE"
KEYSTORE, PASSWORD = "ultronphone.keystore", "ultronphone.keystore.password"


def folder() -> DriveFolder:
    return DriveFolder(agent_work_id()).subfolder(FOLDER, create=True)


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


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "keystore":
        sys.exit(__doc__)
    keystore(Path(sys.argv[2]))
