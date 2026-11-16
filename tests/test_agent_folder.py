"""workings/core/drive.agent_folder (docs/CENTRALISE.md step 7): the agent's Drive paths in one place."""
from ultron.workings.core import drive


class Folder:
    made = []

    def __init__(self, folder_id, http=None):
        self.folder_id = folder_id

    def subfolder(self, name, create=False):
        if name == "MISSING" and not create:
            return None
        Folder.made.append((name, create))
        return Folder(f"{self.folder_id}/{name}")


def test_agent_folder_walks_the_path(monkeypatch):
    monkeypatch.setattr(drive, "DriveFolder", Folder)
    monkeypatch.setenv("AGENT_WORK_FOLDER_ID", "ROOT")
    Folder.made = []
    assert drive.agent_folder().folder_id == "ROOT"
    assert drive.agent_folder("MYNTRA", "LISTING GROUPING", create=True).folder_id == "ROOT/MYNTRA/LISTING GROUPING"
    assert Folder.made == [("MYNTRA", True), ("LISTING GROUPING", True)]
    assert drive.agent_folder("MISSING", "BELOW") is None
