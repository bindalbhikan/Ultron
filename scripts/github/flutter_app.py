"""The Ultron app's builds on GitHub (.github/workflows/flutter-app.yml), kept in Drive AGENT WORK/ULTRON APP.

    python scripts/github/flutter_app.py publish <dir>    every file of <dir> (the APK, the Windows / macOS / Linux
                                                          packages) to Drive, each updated in place under its
                                                          fixed name, then one Telegram note with the links

The Android signing key is the old Ultron Phone app's (scripts/github/android_app.py keystore), so the app
always installs over the one on the phone. The files stay in the owner's Drive, never in this public repo.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ultron.workings.core.config import agent_work_id, env  # noqa: E402
from ultron.workings.core.drive import DriveFolder  # noqa: E402

FOLDER = "ULTRON APP"
# file -> (label, Drive mime type), in the order of the Telegram note
FILES = {
    "ULTRON.apk": ("Android", "application/vnd.android.package-archive"),
    "ULTRON-Windows.zip": ("Windows (unzip, run ULTRON.exe)", "application/zip"),
    "ULTRON-macOS.zip": ("macOS (unzip, open ULTRON; first time: right-click, Open)", "application/zip"),
    "ULTRON-Linux.tar.gz": ("Linux (untar, run bundle/ULTRON)", "application/gzip"),
}


def publish(folder_path: Path) -> None:
    found = {f.name: f for f in folder_path.rglob("*") if f.is_file()}
    missing = [name for name in FILES if name not in found]
    drive = DriveFolder(agent_work_id()).subfolder(FOLDER, create=True)
    lines = []
    for name, (label, mime) in FILES.items():
        if name in found:
            file_id = drive.put(found[name], mime)
            link = f"https://drive.google.com/file/d/{file_id}/view"
            print(f"{name}: uploaded to AGENT WORK/{FOLDER}")
            lines.append(f"• <b>{label}</b>\n{link}")
    for name in missing:                 # a build that failed is named, never silently left out
        lines.append(f"• {FILES[name][0]}: <i>not built this time</i>")
    version = env("APP_VERSION", "?")
    if env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"):
        from ultron.workings.core import telegram
        telegram.send(f"📲 <b>ULTRON app {version} built</b>\n<i>AGENT WORK/{FOLDER}</i>\n\n" + "\n\n".join(lines)
                      + "\n\nAndroid: open the link on the phone and install over the old one.")
    if missing:
        print("not built:", ", ".join(missing))
    if env("APP_UPDATES_API") and env("DASHBOARD_TOKEN"):
        from app_updates import publish_updates
        publish_updates(found, api=env("APP_UPDATES_API").rstrip("/"), token=env("DASHBOARD_TOKEN"),
                        version=version, build=int(env("BUILD_NUMBER")))



if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "publish":
        sys.exit(__doc__)
    publish(Path(sys.argv[2]))
