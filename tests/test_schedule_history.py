"""Schedule revisions affect only starts due while that revision was active."""
from datetime import date, datetime

from ultron.workings.work_schedule import pipeline as schedule



def test_report_job_receives_shared_schedule_credentials():
    from pathlib import Path
    import yaml
    path = Path(__file__).resolve().parents[1] / ".github/workflows/agent-watch.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    variables = workflow["jobs"]["schedule"]["env"]
    assert variables["DASHBOARD_URL"] == "${{ secrets.DASHBOARD_URL }}"
    assert variables["DASHBOARD_TOKEN"] == "${{ secrets.DASHBOARD_TOKEN }}"


def change(at, target, enabled=True, *, day=0):
    return {"at": datetime.fromisoformat(at), "origin": 540, "target": target, "enabled": enabled, "day": day}


def test_rescheduling_does_not_rewrite_previous_days_or_already_due_starts():
    task = schedule.Task("Report", "report.yml", (540,), "DAILY",
                         changes=(change("2026-11-25T09:30:00", 600),))
    assert task.slots_on(date(2026, 11, 24)) == (540,)
    assert task.slots_on(date(2026, 11, 25)) == (540, 600)
    assert task.slots_on(date(2026, 11, 26)) == (600,)


def test_pausing_and_resuming_respect_the_original_slot_time():
    task = schedule.Task("Report", "report.yml", (540,), "DAILY", changes=(
        change("2026-11-25T08:00:00", 540, False),
        change("2026-11-26T10:00:00", 540),
    ))
    assert task.slots_on(date(2026, 11, 24)) == (540,)
    assert task.slots_on(date(2026, 11, 25)) == ()
    assert task.slots_on(date(2026, 11, 26)) == ()
    assert task.slots_on(date(2026, 11, 27)) == (540,)


def test_one_monthly_entry_does_not_change_another_day():
    task = schedule.Task("Grouping", "grouping.yml", (540,), "MONTHLY", days=(1, 4),
                         changes=(change("2026-11-24T08:00:00", 600, day=1),))
    assert task.slots_on(date(2026, 12, 1)) == (600,)
    assert task.slots_on(date(2026, 12, 4)) == (540,)
    assert task.slots_on(date(2026, 12, 2)) == ()
