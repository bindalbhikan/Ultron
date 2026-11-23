"""GitHub run times reach the model in the owner's time as well as UTC (the agent told UTC times as theirs)."""
from datetime import datetime, timezone

from ultron.integrations.github import brief, local_time


def test_local_time_is_the_machine_zone():
    want = datetime(2026, 11, 23, 4, 0, tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %z")
    assert local_time("2026-11-23T04:00:00Z") == want
    assert local_time(None) is None and local_time("bad") is None
    r = brief({"id": 1, "run_started_at": "2026-11-23T04:00:00Z", "updated_at": "2026-11-23T04:30:00Z"})
    assert r["started"] == "2026-11-23T04:00:00Z" and r["started_local"] == want and r["minutes"] == 30.0
