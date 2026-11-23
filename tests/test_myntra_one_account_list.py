"""One Myntra account list (portals/myntra.py SELLERS / ACCOUNTS, 23 Nov 2026): no working keeps its own copy, so a
new account (EXIM) joins every Myntra working in one place."""
import re
from pathlib import Path

from ultron.workings.portals import myntra as mp

SRC = Path(__file__).resolve().parents[1] / "src" / "ultron" / "workings"


def test_no_working_keeps_its_own_copy_of_the_accounts():
    copies = []
    for p in SRC.rglob("*.py"):
        if p.name == "myntra.py" and p.parent.name == "portals":
            continue
        text = p.read_text(encoding="utf-8")
        if re.search(r'"MAIN",\s*"DBCC",\s*"FMCC"', text) or re.search(r'"19170"\s*:', text):
            copies.append(str(p.relative_to(SRC)))
    assert copies == []


def test_exim_is_known_and_joins_the_workings_once_its_login_is_saved():
    assert mp.SELLERS["EXIM"] == 109704
    assert list(mp.ACCOUNTS) == ["MAIN", "DBCC", "FMCC"]
    assert all(mp.ACCOUNTS[a] == mp.SELLERS[a] for a in mp.ACCOUNTS)
