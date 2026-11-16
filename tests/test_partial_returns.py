"""The 15th keeps the next month's 1st-14th returns as a PARTIAL report that never replaces a whole one."""
from datetime import date
from pathlib import Path

from ultron.workings.core import portal_reports as pr


class Folder:
    def __init__(self, names):
        self.names = dict.fromkeys(names, {"id": "x"})

    def children(self):
        return self.names


def test_partial_saved_when_the_month_has_no_whole_report(monkeypatch, tmp_path):
    saved = []
    monkeypatch.setattr(pr, "month_folder", lambda *a, **k: Folder([]))
    monkeypatch.setattr(pr, "save", lambda *a, **k: saved.append((a, k)) or "name")
    f = tmp_path / "r.csv"
    f.write_text("x")
    assert pr.save_partial("MYNTRA", date(2026, 11, 1), "return", f, "MAIN") == "name"
    assert saved and saved[0][1] == {"partial": True}


def test_whole_report_stays(monkeypatch, tmp_path):
    whole = pr.file_name("MYNTRA", date(2026, 11, 1), "return", "MAIN", ".csv")
    monkeypatch.setattr(pr, "month_folder", lambda *a, **k: Folder([whole]))
    monkeypatch.setattr(pr, "save", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not save")))
    f = tmp_path / "r.csv"
    f.write_text("x")
    assert pr.save_partial("MYNTRA", date(2026, 11, 1), "return", f, "MAIN") == ""
    assert pr.save_partial("MYNTRA", date(2026, 11, 1), "return", None, "MAIN") == ""
    assert isinstance(Path(whole), Path)
