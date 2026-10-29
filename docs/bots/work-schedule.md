# Agent work schedule — `python run.py work-schedule`

**When**: after every bot run (`work-schedule.yml`, `workflow_run` on the bot workflows; not after
the inventory push, whose runs the next update counts). By hand: run the workflow (`month` =
YYYY-MM rebuilds that month).

* Drive `BINDAL EXPORTS/AGENT WORK/AGENT REPORT WORK SCHEDULE REPORT.xlsx`:
  * **SCHEDULE**: every scheduled task A to Z, SR / TASK NAME / TIME / DAILY/WEEKLY / WORK (what it
    does, `WORK` in the pipeline; the month sheets have WORK as their last column). The list is `TASKS`
    in `work_schedule/pipeline.py`, the same as `SCHEDULE` in `worker/src/worker.js`: a new
    scheduled task goes in both.
  * **One sheet a month** (`OCT-26`): the same columns, then a column per day (header row 1,
    weekdays row 2, tasks from row 3, no title rows; SCHEDULE left-aligned: the layout set by hand
    on 28 Oct 2026, kept by every update). A box on each day
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
* **LOGS** tab: every bot run of the last 31 days, newest first (DATE, START, BOT, MINUTES, RESULT,
  ERROR, HYPER LOG, GITHUB RUN), from the GitHub run history; the agent's own housekeeping runs
  (Agent watch / chat / work schedule) left out. HYPER LOG links the run's detailed log on Drive;
  ERROR is read from the log of a failed run.

## Hyper logs (`core/hyperlog.py`)

Every bot run (`run_bot`) writes a detailed log: header (bot, arguments, GitHub run, commit,
host), everything the bot's loggers say down to DEBUG with time to the millisecond, thread,
module, function and line, every HTTP call (method, host/path without the query, status, seconds,
size) and a footer (OK / FAIL, exit code, minutes, the full traceback). Passwords, tokens,
cookies, Bearer keys, Telegram bot tokens and long keys are masked first. On GitHub (or locally
with `HYPERLOG_UPLOAD=1`) it goes to Drive `AGENT WORK/AGENT LOGS/<OCT-26>/<29-10-26>/<BOT>
<05.31 PM> <OK|FAIL> #<run id>.log` through the owner's OAuth token (every bot workflow has the
Drive secrets for it). `HYPERLOG=0` turns it off. An upload problem never fails the run.

