# Agent work schedule — `python run.py work-schedule`

**When**: after every bot run (`work-schedule.yml`, `workflow_run` on the bot workflows; not after
the inventory push, whose runs the next update counts). By hand: run the workflow (`month` =
YYYY-MM rebuilds that month).

* Drive `BINDAL EXPORTS/AGENT WORK/AGENT REPORT WORK SCHEDULE REPORT.xlsx`:
  * **SCHEDULE**: every scheduled task, SR / TASK NAME / TIME / DAILY/WEEKLY. The list is `TASKS`
    in `work_schedule/pipeline.py`, the same as `SCHEDULE` in `worker/src/worker.js`: a new
    scheduled task goes in both.
  * **One sheet a month** (`OCT-26`): the same columns, then a column per day. A box on each day
    the task is due: ☑ (green) once its workflow ran successfully, ☐ while not, red once the day's
    slot is 12 h (`SLOT_HOURS`) past, grey = not due that day.
* Filled from the GitHub Actions run history, not by the bots: one writer (runs queue in the
  `work-schedule` concurrency group), and every update rebuilds this month (and last month, early
  on the 1st) from all successful runs, so a missed update fixes itself.
* A run counts for the latest slot of its workflow at or before its start, within 12 h (a re-run
  by hand after a failure ticks the box too). Inventory push: ☑ when all 8 runs (6 AM - 3 AM) passed.
* No box before a workflow's first successful run (the repo's history starts 24 Oct 2026, 10:25 PM IST).
* Only this month's sheet (and SCHEDULE) is rewritten; older month sheets stay as they are. Edits
  made by hand in the current month's sheet are overwritten.
