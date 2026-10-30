"""Copy values from the local .env into the repo's GitHub Actions secrets (same names), without the
GitHub CLI (scripts/myntra/myntra_session.py secret_by_api). The values are never printed.

    python scripts/github/env_secrets.py SMS_WEBAPP_URL SMS_WEBAPP_KEY
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "myntra"))

from ultron.workings.core.config import env, load_dotenv  # noqa: E402
from myntra_session import secret_by_api  # noqa: E402


def main(names: list[str]) -> int:
    load_dotenv()
    bad = 0
    for name in names:
        value = env(name)
        if not value:
            print(f"{name}: not in .env")
            bad += 1
            continue
        ok, why = secret_by_api(name, value)
        print(f"{name}: {'set' if ok else 'NOT set - ' + why}")
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
