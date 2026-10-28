"""Agent work schedule: Drive AGENT WORK/AGENT REPORT WORK SCHEDULE REPORT.xlsx.

SCHEDULE: every scheduled bot task (SR, TASK NAME, TIME, DAILY/WEEKLY), the same list as SCHEDULE in
worker/src/worker.js. One sheet a month (OCT-26): the same columns, then a column per day of the
month with a check box on the days the task is due: ☑ once the task's GitHub workflow ran
successfully for that slot, ☐ while it has not (red once the day is over).

Filled from the GitHub Actions run history, not by the bots themselves: work-schedule.yml runs after
every bot run (workflow_run) and rebuilds this month's sheet (and last month's, for the runs after
midnight) from the successful runs (no box before a workflow's first run: the task did not exist yet), so the bots never write the file at the same time and a missed
update is caught by the next one. A run counts for the latest slot of its workflow at or before
its start, up to SLOT_HOURS (12) later (a re-run by hand after a failure counts too).
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import requests

from ..core.app import run_bot
from ..core.config import env, num

log = logging.getLogger("bindal.work_schedule")

AGENT_WORK = "1uO-aOha_QKkI3f19EA7sweYPgkjMukZI"   # Drive BINDAL EXPORTS/AGENT WORK
WORKBOOK = "AGENT REPORT WORK SCHEDULE REPORT.xlsx"
IST = timezone(timedelta(hours=5, minutes=30))
DONE, DUE = "☑", "☐"
COLUMNS = ["SR", "TASK NAME", "TIME", "DAILY/WEEKLY"]
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


@dataclass(frozen=True)
class Task:
    name: str
    workflow: str                     # .github/workflows/<file>
    slots: tuple[int, ...]            # IST minutes after the day's midnight (past 1440 = next day)
    every: str                        # the DAILY/WEEKLY column
    weekdays: tuple[int, ...] = ()    # Python weekday(): 0 = Monday
    day: int = 0                      # day of the month

    def due(self, d: date) -> bool:
        return (not self.weekdays or d.weekday() in self.weekdays) and (not self.day or d.day == self.day)

    @property
    def time(self) -> str:
        if len(self.slots) > 1:
            return "every 3 hours, 6 AM - 3 AM"
        return datetime.combine(date.today(), time(self.slots[0] // 60, self.slots[0] % 60)).strftime(
            "%I:%M %p").lstrip("0")


def _at(h: int, m: int = 0) -> tuple[int, ...]:
    return (h * 60 + m,)


MON_SAT = (0, 1, 2, 3, 4, 5)
# SCHEDULE in worker/src/worker.js, by time of day (worker weekdays 0 = Sunday -> here 6)
TASKS = [
    Task("SJIT report request", "sale.yml", _at(7), "DAILY"),
    Task("Myntra SPF report request", "myntra-spf.yml", _at(7), "DAILY"),
    Task("Return analysis report request", "returns.yml", _at(7), "MONTHLY (15th)", day=15),
    Task("Myntra SPF master", "myntra-spf.yml", _at(9), "DAILY"),
    Task("AJIO SPF (tickets + replies)", "ajio-spf.yml", _at(9), "WEEKLY (WED, SAT)", weekdays=(2, 5)),
    Task("AJIO SPF master update", "ajio-spf.yml", _at(9), "DAILY (not WED, SAT)", weekdays=(0, 1, 3, 4, 6)),
    Task("AJIO Ads / TOT gap", "ajio-ads.yml", _at(9), "MONTHLY (3rd)", day=3),
    Task("AJIO Ads / TOT gap (if missed)", "ajio-ads.yml", _at(9), "MONTHLY (5th)", day=5),
    Task("Morning report", "morning.yml", _at(9, 30), "DAILY"),
    Task("Myntra courier OTP", "myntra-otp.yml", _at(10), "DAILY"),
    Task("Myntra daily reports", "myntra-reports.yml", _at(10), "DAILY"),
    Task("Stock-out alert", "stock.yml", _at(10), "DAILY"),
    Task("Myntra zero TD", "myntra-zero-td.yml", _at(10), "MON-SAT", weekdays=MON_SAT),
    Task("Weekly review", "weekly.yml", _at(10, 15), "WEEKLY (MON)", weekdays=(0,)),
    Task("Myntra courier OTP retry", "myntra-otp.yml", _at(11), "DAILY"),
    Task("Dead stock report", "deadstock.yml", _at(11), "MONTHLY (1st)", day=1),
    Task("Monthly MIS", "mis.yml", _at(11), "MONTHLY (2nd)", day=2),
    Task("Listing health", "listings.yml", _at(11, 30), "DAILY"),
    Task("SLA warning", "sla.yml", _at(12), "DAILY"),
    Task("Myntra zero TD", "myntra-zero-td.yml", _at(14), "MON-SAT", weekdays=MON_SAT),
    Task("Return analysis", "returns.yml", _at(14), "MONTHLY (15th)", day=15),
    Task("SLA warning", "sla.yml", _at(15), "DAILY"),
    Task("Daily sale report", "sale.yml", _at(15, 30), "DAILY"),
    Task("Myntra zero TD", "myntra-zero-td.yml", _at(17), "MON-SAT", weekdays=MON_SAT),
    Task("Myntra VMS report", "vms.yml", _at(17, 30), "DAILY"),
    Task("AJIO TAT daily update", "ajio-tat.yml", _at(17, 30), "DAILY"),
    Task("Label check", "labels.yml", _at(18), "DAILY"),
    Task("Myntra courier scorecard", "myntra-tat.yml", _at(18, 30), "DAILY"),
    Task("Evening summary", "evening.yml", _at(20), "DAILY"),
    Task("OMSGuru inventory push", "inv-push.yml", tuple(h * 60 for h in range(6, 28, 3)), "DAILY (8 times)"),
]


# ------------------------------------------------------------------ GitHub run history

def github():
    """(repo, session): GITHUB_REPOSITORY / GITHUB_TOKEN in Actions; locally the origin remote and
    git's stored credential."""
    repo, token = env("GITHUB_REPOSITORY"), env("GITHUB_TOKEN")
    if not repo:
        url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True).stdout
        repo = url.strip().split("github.com")[-1].lstrip(":/").removesuffix(".git")
    if not token:
        out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                             capture_output=True, text=True).stdout
        token = next((x[9:] for x in out.splitlines() if x.startswith("password=")), "")
    s = requests.Session()
    s.headers.update({"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"})
    return repo, s


def successful_runs(workflow: str, since: date, repo: str, s) -> list[datetime]:
    """Start times (IST) of the workflow's successful runs created from `since`."""
    out, page = [], 1
    while True:
        r = s.get(f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs", timeout=60,
                  params={"status": "success", "created": f">={since}", "per_page": 100, "page": page})
        if r.status_code == 404:
            log.warning("No workflow %s on GitHub", workflow)
            return out
        r.raise_for_status()
        runs = r.json().get("workflow_runs") or []
        out += [datetime.fromisoformat((x.get("run_started_at") or x["created_at"]).replace("Z", "+00:00"))
                .astimezone(IST).replace(tzinfo=None) for x in runs]
        if len(runs) < 100:
            return out
        page += 1


def done_slots(first: date, last: date, runs: dict[str, list[datetime]]) -> set[tuple[int, date, int]]:
    """(task index, day, slot) done: a successful run of the task's workflow at or after the slot,
    before the workflow's next slot and within SLOT_HOURS (12)."""
    window = timedelta(hours=num("SLOT_HOURS", 12))
    slots: dict[str, list[tuple[datetime, int, date, int]]] = {}
    d = first - timedelta(days=1)
    while d <= last + timedelta(days=1):
        for i, t in enumerate(TASKS):
            if t.due(d):
                for k, m in enumerate(t.slots):
                    slots.setdefault(t.workflow, []).append((datetime.combine(d, time()) + timedelta(minutes=m), i, d, k))
        d += timedelta(days=1)
    done = set()
    for wf, items in slots.items():
        items.sort()
        starts = sorted({at for at, *_ in items})
        for run in runs.get(wf, []):
            past = [at for at in starts if at <= run]
            if past and run - past[-1] <= window:
                done |= {(i, d, k) for at, i, d, k in items if at == past[-1]}
    return done


# ------------------------------------------------------------------ workbook

def month_sheet(month: date) -> str:
    return f"{month:%b-%y}".upper()


def write_schedule(wb) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill
    if "SCHEDULE" in wb.sheetnames:
        del wb["SCHEDULE"]
    for name in ("Sheet1", "Sheet"):
        if name in wb.sheetnames and wb[name].max_row == 1 and wb[name]["A1"].value is None:
            del wb[name]
    ws = wb.create_sheet("SCHEDULE", 0)
    ws.append(COLUMNS)
    for n, t in enumerate(TASKS, 1):
        ws.append([n, t.name, t.time, t.every])
    head = PatternFill("solid", fgColor="1F4E78")
    for c in ws[1]:
        c.font, c.fill, c.alignment = Font(bold=True, color="FFFFFF"), head, Alignment(horizontal="center")
    for col, width in zip("ABCD", (6, 34, 26, 22)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"


def write_month(wb, month: date, done: set, now: datetime, since: dict[str, datetime]) -> None:
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    name = month_sheet(month)
    at = sorted([n for n in wb.sheetnames if n != "SCHEDULE"] + [name],
                key=lambda n: datetime.strptime(n.title(), "%b-%y") if n[:3].isalpha() and "-" in n else datetime.max)
    if name in wb.sheetnames:
        del wb[name]
    ws = wb.create_sheet(name, 1 + at.index(name))
    days = [month + timedelta(days=i) for i in range(31) if (month + timedelta(days=i)).month == month.month]
    ws.append([f"AGENT WORK SCHEDULE · {month:%B %Y}".upper()])
    ws.append([f"{DONE} done (the bot ran successfully)   {DUE} not done yet   red = missed   blank = not due that day"
               f"   ·   updated {now:%d-%m-%y %I:%M %p}"])
    ws.append(COLUMNS + [d.day for d in days])
    ws.append([""] * len(COLUMNS) + [DAYS[d.weekday()] for d in days])
    green, red, grey = (PatternFill("solid", fgColor=c) for c in ("C6EFCE", "FFC7CE", "F2F2F2"))
    for n, t in enumerate(TASKS):
        row = [n + 1, t.name, t.time, t.every]
        for d in days:
            ok = all((n, d, k) in done for k in range(len(t.slots)))
            began = datetime.combine(d, time()) + timedelta(minutes=t.slots[0]) >= since.get(t.workflow, datetime.max)
            row.append("" if not t.due(d) or not (ok or began) else DONE if ok else DUE)
        ws.append(row)
        r = ws.max_row
        for j, d in enumerate(days):
            c = ws.cell(r, len(COLUMNS) + 1 + j)
            c.alignment = Alignment(horizontal="center")
            last_slot = datetime.combine(d, time()) + timedelta(minutes=t.slots[-1], hours=num("SLOT_HOURS", 12))
            if c.value == DONE:
                c.fill, c.font = green, Font(color="006100", size=12)
            elif c.value == DUE and now > last_slot:
                c.fill, c.font = red, Font(color="9C0006", size=12)
            elif c.value == "":
                c.fill = grey
    head = PatternFill("solid", fgColor="1F4E78")
    thin = Side(style="thin", color="BFBFBF")
    for r in (3, 4):
        for c in ws[r]:
            c.font, c.fill, c.alignment = Font(bold=True, color="FFFFFF", size=9), head, Alignment(horizontal="center")
    for row in ws.iter_rows(min_row=3, max_row=ws.max_row):
        for c in row:
            c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"].font = Font(italic=True, size=9, color="595959")
    for col, width in zip("ABCD", (5, 32, 24, 20)):
        ws.column_dimensions[col].width = width
    for j in range(len(days)):
        ws.column_dimensions[get_column_letter(len(COLUMNS) + 1 + j)].width = 5
    ws.freeze_panes = ws.cell(5, len(COLUMNS) + 1)


def build(path: Path, months: list[date], now: datetime) -> dict:
    from openpyxl import Workbook, load_workbook
    wb = load_workbook(path) if path.exists() else Workbook()
    first, last = min(months), max(months)
    last = (last.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    repo, s = github()
    # from further back: a workflow's first run marks when the task began (no box before it)
    runs = {wf: successful_runs(wf, first - timedelta(days=70), repo, s) for wf in {t.workflow for t in TASKS}}
    since = {wf: min(r) for wf, r in runs.items() if r}
    done = done_slots(first, last, runs)
    write_schedule(wb)
    for m in months:
        write_month(wb, m, done, now, since)
    wb.active = wb.sheetnames.index(month_sheet(max(months)))
    wb.save(path)
    today = now.date()
    due = [(i, k) for i, t in enumerate(TASKS) if t.due(today) for k in range(len(t.slots))]
    return {"today_due": len(due), "today_done": sum((i, today, k) in done for i, k in due)}


def run(args) -> int:
    from ..core.drive import DriveFile, DriveFolder
    now = datetime.now(IST).replace(tzinfo=None) if not args.at else datetime.fromisoformat(args.at)
    months = sorted({(now - timedelta(hours=num("SLOT_HOURS", 12) + 18)).date().replace(day=1),
                     now.date().replace(day=1)})
    if args.month:
        months = [date.fromisoformat(args.month + "-01")]
    work = Path(tempfile.mkdtemp(prefix="work_schedule_")) / WORKBOOK
    if args.local:
        work = Path(args.local)
        stats = build(work, months, now)
        print(f"{work}: {', '.join(map(month_sheet, months))}; today {stats['today_done']}/{stats['today_due']} done")
        return 0
    root = DriveFolder(env("AGENT_WORK_FOLDER_ID", AGENT_WORK))
    found = root.children().get(WORKBOOK)
    if not found:
        raise RuntimeError(f"{WORKBOOK} not found in AGENT WORK on Drive")
    drive = DriveFile(found["id"], root.http)
    drive.download(work, need_edit=True)
    stats = build(work, months, now)
    drive.upload(work)
    print(f"{WORKBOOK}: {', '.join(map(month_sheet, months))} updated; today {stats['today_done']}/"
          f"{stats['today_due']} done. {drive.url}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--month", help="rebuild this month only, YYYY-MM (default this month, and last month "
                                   "early on the 1st)")
    p.add_argument("--at", help="as if now were this IST time, YYYY-MM-DDTHH:MM (tests)")
    p.add_argument("--local", help="write this local xlsx instead of the Drive workbook")
    return run_bot("Agent work schedule", p, run, argv)


if __name__ == "__main__":
    raise SystemExit(main())
