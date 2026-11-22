"""A run's files never go inside the source code."""
from pathlib import Path

from ultron.core import paths


def test_output_is_outside_the_source_code(monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    monkeypatch.delenv("ULTRON_OUTPUT", raising=False)
    assert repo not in paths.output_root().parents
    monkeypatch.setenv("ULTRON_OUTPUT", str(repo / "output"))           # GitHub's runner (ci_run.sh)
    assert paths.output_root() == (repo / "output").resolve()
