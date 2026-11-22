"""Where a run's files go: never inside the source code.

output_root(): ULTRON_OUTPUT when set (GitHub's runner: scripts/github/ci_run.sh sets it to the checkout's output/,
which it encrypts as the run's artifact), else the user's data folder of this machine (platformdirs:
%LOCALAPPDATA%\\Ultron\\output on Windows, ~/.local/share/Ultron/output on Linux and Termux,
~/Library/Application Support/Ultron/output on a Mac). Results, logs and the local caches live there; they hold
customer data and are never in the repository.
"""
from __future__ import annotations

import os
from pathlib import Path


def output_root() -> Path:
    if os.getenv("ULTRON_OUTPUT"):
        return Path(os.environ["ULTRON_OUTPUT"]).expanduser().resolve()
    from platformdirs import user_data_path
    return user_data_path("Ultron", appauthor=False) / "output"
