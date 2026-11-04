"""The repo is public: no Drive file or folder id in the code (they are settings)."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVE_ID = re.compile(r"""['"]1[A-Za-z0-9_-]{30,}['"]""")


class NoDriveIds(unittest.TestCase):
    def test_tracked_code_holds_no_drive_id(self):
        names = subprocess.run(["git", "ls-files", "src", "scripts", "worker", "android app/apps-script", ".github"],
                               cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
        hits = []
        for name in names:
            path = ROOT / name
            if path.suffix in (".py", ".js", ".gs", ".toml", ".yml", ".sh") and path.is_file():
                hits += [name for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if DRIVE_ID.search(line)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
