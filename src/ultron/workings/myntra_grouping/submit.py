"""Submitting the pending colour groups on the Myntra partner portal, and keeping the record of it.

  sync_jobs     every style-grouping job on the portal goes into the record (also those uploaded by
                hand: BY = Portal, their style ids read from the job's input file), and the status and
                counts of every job are read again (WAITING, APPROVAL_PENDING, COMPLETED,
                IN_PROGRESS, PARTIAL_COMPLETE, FAILED, REJECTED). Myntra approves an upload before it goes
                live.
  group state   for Telegram: the newest job of a group decides, never an older one; a group with nothing
                pending on myntra.com is DONE, whatever its old jobs say.
  submit        the upload files of TEMPLATES/<day>/ACC-<seller id>/ are uploaded on their account
                (only with --submit, the owner's call). skip_reason says what is not sent.
  The record    Drive AGENT WORK/MYNTRA/LISTING GROUPING/GROUPING SUBMISSIONS.xlsx, one row per upload,
                kept for good, newest first.
  reasons       Drive .../GROUPING REASONS.xlsx: every row of every finished job's result report (style, what
                the portal said), kept for good; a finished job's report is read once.
  apply         the master gets a SUBMISSIONS sheet and account sheets in the owner's layout (2 Nov 2026):
                on a style not grouped yet (NOT DONE), its own newest job and reason. It can run again on a
                finished master (--status).
"""
from __future__ import annotations

import io
import logging
import re
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger("bindal.myntra_grouping")

RECORD = "GROUPING SUBMISSIONS.xlsx"
COLS = ["SUBMITTED ON", "TIME", "ACCOUNT", "SELLER ID", "UNIQUE ID", "BRAND", "ARTICLE TYPE", "FILE", "STYLES",
        "STYLE IDS", "JOB ID", "JOB STATUS", "TOTAL RECORDS", "PROCESSED RECORDS", "ERRED RECORDS", "BY", "PORTAL REMARK"]
SELLER_OF = {"MAIN": "19170", "DBCC": "32207", "FMCC": "35426"}
ACCOUNT_OF = {v: k for k, v in SELLER_OF.items()}
FINISHED = {"COMPLETED", "PARTIAL_COMPLETE", "FAILED", "REJECTED"}
# An approved job can take days to show on myntra.com (2 Nov 2026: 35 of 143 jobs approved that day were
# fully there hours later), so it is not sent again for this long; a failed upload is free to try again after it.
WAIT_DAYS = 7
REASONS = "GROUPING REASONS.xlsx"
REASON_COLS = ["JOB ID", "SUBMITTED ON", "ACCOUNT", "SELLER ID", "JOB STATUS", "UNIQUE ID", "STYLE ID", "GROUPING TYPE", "REMARK", "GROUP ID"]
EMPTY_REPORT = "the portal's report has no rows"
# The account sheets of the master, the owner's layout (2 Nov 2026); HISTORY keeps every column of the check.
LAYOUT = ["Unique ID", "Group Type", "Article Type", "Brand", "Style ID", "SKU", "FINAL SKU", "GROUPING REMARK", "STATUS", "INV", "SALE",
          "ACTION", "PORTAL COLOR", "JOB ID", "JOB STATUS", "JOB SUBMITED DATE", "PORTAL REMARK"]
DONE, FRESH, WAITING, APPROVED, CHECK = "DONE", "FRESH", "WAITING ON MYNTRA", "APPROVED, SITE NOT UPDATED", "APPROVED, NOT ON SITE: CHECK"
PARTIAL, FAILED, REJECTED = "PARTIAL", "FAILED", "REJECTED"


def read_record(path: Path | None) -> pd.DataFrame:
    if path and path.exists():
        return pd.read_excel(path, sheet_name="SUBMISSIONS", dtype=str).reindex(columns=COLS)
    return pd.DataFrame(columns=COLS, dtype=object)


def template_rows(path: Path) -> tuple[str, list[str]]:
    """(unique id, style ids) of one upload file."""
    df = pd.read_excel(path, dtype=str)
    uid = str(df.iloc[0, 0]).strip() if len(df) else ""
    return uid, [str(x).replace(".0", "").strip() for x in df.iloc[:, 2].dropna()]


def _when(value) -> tuple[str, str]:
    """(date, time) in IST of a job's createdAt (the portal answers UTC, ISO text or epoch ms)."""
    try:
        t = pd.to_datetime(value, unit="ms") if str(value).isdigit() else pd.to_datetime(value)
        t = t.tz_convert(None) if t.tzinfo else t
        t = t + timedelta(hours=5, minutes=30)
        return f"{t:%Y-%m-%d}", f"{t:%H:%M}"
    except (ValueError, TypeError):
        return str(value)[:10], ""


def _job_styles(job: dict) -> tuple[str, list[str]]:
    """(unique id, style ids) from a job's input file; empty when it cannot be read."""
    url = (job.get("metaData") or {}).get("signedInputFilePath")
    if not url:
        return "", []
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        df = pd.read_excel(io.BytesIO(r.content), dtype=str)
        return str(df.iloc[0, 0]).strip(), [str(x).replace(".0", "").strip() for x in df.iloc[:, 2].dropna()]
    except Exception as exc:  # noqa: BLE001 - the job is still recorded
        log.info("Input file of job %s not read: %s", job.get("id"), str(exc)[:100])
        return "", []


def sync_jobs(record: pd.DataFrame, accounts: list[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """The portal's jobs into the record, every status read again; problems, one line each."""
    from ..portals import myntra as mp
    from ..return_analysis.sources import env, myntra_portal
    record, problems, new = record.copy(), [], []
    for account in accounts or list(SELLER_OF):
        try:
            portal = myntra_portal(account)
            jobs, page = [], 1
            while True:         # every page: a job past the first would keep its old status for good
                got = portal.style_grouping_jobs(200, page)
                jobs += got
                if len(got) < 200:
                    break
                page += 1
            mp.save_to_worker(env, portal.cookies(), account)
        except Exception as exc:  # noqa: BLE001 - one account never stops the others
            problems.append(f"{account}: grouping jobs not read ({str(exc).splitlines()[0][:100]})")
            continue
        known = set(record["JOB ID"].astype(str))
        for j in jobs:
            jid = str(j.get("id"))
            counts = [str(j.get("status") or ""), str(j.get("totalRecords") or 0), str(j.get("processedRecords") or 0),
                      str(j.get("erredRecords") or 0)]
            day, at = _when(j.get("createdAt"))
            if jid in known:     # the portal's own time: the clock of the run that uploaded can be UTC
                record.loc[record["JOB ID"].astype(str) == jid,
                           ["SUBMITTED ON", "TIME", "JOB STATUS", "TOTAL RECORDS", "PROCESSED RECORDS", "ERRED RECORDS"]] = [day, at, *counts]
                continue
            uid, styles = _job_styles(j)
            new.append({"SUBMITTED ON": day, "TIME": at, "ACCOUNT": account, "SELLER ID": SELLER_OF[account],
                        "UNIQUE ID": uid, "BRAND": "", "ARTICLE TYPE": "", "FILE": "", "STYLES": str(len(styles)),
                        "STYLE IDS": ", ".join(styles), "JOB ID": jid, "JOB STATUS": counts[0], "TOTAL RECORDS": counts[1],
                        "PROCESSED RECORDS": counts[2], "ERRED RECORDS": counts[3], "BY": "Portal"})
    if new:
        record = pd.concat([record, pd.DataFrame(new, columns=COLS)], ignore_index=True)
    return record, problems


def read_reasons(path: Path | None) -> pd.DataFrame:
    if path and path.exists():
        return pd.read_excel(path, sheet_name="REASONS", dtype=str).reindex(columns=REASON_COLS)
    return pd.DataFrame(columns=REASON_COLS, dtype=object)


def _report_rows(link: str) -> list[dict]:
    """The rows of one job's result report. Its columns differ: Unique ID, Style ID, Grouping Type, Remarks,
    GroupId; a rejected job's uniqueId, styleId, groupingType, rejectReason. A long report repeats its header.
    When the portal could not read the upload at all, its error stands alone in the first column."""
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(requests.get(link, timeout=60).content))
    df = pd.read_csv(z.open(z.namelist()[0]), dtype=str)
    df.columns = [re.sub(r"[^a-z]", "", str(c).lower()) for c in df.columns]
    out = []
    for r in df.fillna("").to_dict("records"):
        style = str(r.get("styleid", "")).replace(".0", "").strip()
        remark = str(r.get("remarks", r.get("rejectreason", ""))).strip()
        unique = str(r.get("uniqueid", "")).strip()
        if style.lower().replace(" ", "") == "styleid":
            continue
        if not style and not remark and "exception" in unique.lower():
            remark, unique = unique.rsplit("Exception:", 1)[-1].strip(), ""
        if not (style or remark):
            continue
        out.append({"UNIQUE ID": unique, "STYLE ID": style, "GROUPING TYPE": str(r.get("groupingtype", "")).strip(),
                    "REMARK": remark, "GROUP ID": str(r.get("groupid", "")).replace(".0", "").strip()})
    return out


def update_reasons(record: pd.DataFrame, reasons: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Every finished job's report not read yet into the reasons, JOB STATUS brought up to date, and PORTAL REMARK
    of each job from them; (record, reasons, problems). A report that cannot be read is tried again next run."""
    from ..return_analysis.sources import myntra_portal
    record, portals, new, unread = record.copy(), {}, [], 0
    have = set(reasons["JOB ID"].astype(str))
    numbered = record["JOB ID"].astype(str).str.fullmatch(r"\d+")
    for _, r in record[numbered & record["JOB STATUS"].isin(FINISHED)].iterrows():
        jid = str(r["JOB ID"])
        if jid in have:
            continue
        try:
            if r["ACCOUNT"] not in portals:
                portals[r["ACCOUNT"]] = myntra_portal(r["ACCOUNT"])
            rows = _report_rows(portals[r["ACCOUNT"]].style_grouping_report(int(jid)))
        except Exception as exc:  # noqa: BLE001 - the others still count
            unread += 1
            log.info("Report of job %s not read: %s", jid, str(exc)[:100])
            continue
        common = {"JOB ID": jid, "SUBMITTED ON": r["SUBMITTED ON"], "ACCOUNT": r["ACCOUNT"], "SELLER ID": r["SELLER ID"]}
        new += [{**common, **row} for row in rows or [{"REMARK": EMPTY_REPORT}]]
    if new:
        reasons = pd.concat([reasons, pd.DataFrame(new, columns=REASON_COLS)], ignore_index=True)
    status = dict(zip(record["JOB ID"].astype(str), record["JOB STATUS"]))
    reasons["JOB STATUS"] = reasons["JOB ID"].astype(str).map(status)
    said = reasons[~reasons["REMARK"].astype(str).str.upper().isin(["SUCCESS", "", "NAN"])]
    joined = said.groupby(said["JOB ID"].astype(str))["REMARK"].agg(lambda x: " | ".join(dict.fromkeys(x.astype(str)))[:300])
    record["PORTAL REMARK"] = record["JOB ID"].astype(str).map(joined).fillna("")
    return record, reasons, [f"{unread} job reports not read: tried again next run"] if unread else []


def jobs_of(record: pd.DataFrame) -> list[dict]:
    """Every job the portal took, oldest first (by job id: the portal numbers them in order)."""
    out = []
    for _, r in record.iterrows():
        jid = str(r["JOB ID"]).replace(".0", "")
        if not jid.isdigit():
            continue
        remark = r["PORTAL REMARK"]
        out.append({"id": int(jid), "seller": str(r["SELLER ID"]), "day": str(r["SUBMITTED ON"])[:10], "status": str(r["JOB STATUS"]),
                    "styles": {s for s in str(r["STYLE IDS"]).split(", ") if s and s != "nan"},
                    "remark": "" if pd.isna(remark) else str(remark)})
    return sorted(out, key=lambda j: j["id"])


def _recent(job: dict, today: date) -> bool:
    try:
        return (today - date.fromisoformat(job["day"])).days <= WAIT_DAYS
    except ValueError:
        return False


def skip_reason(seller: str, styles: list[str], jobs: list[dict], today: date, again: bool = False) -> str:
    """Why this upload is not sent now ("" = send it). Only the newest attempt of the same styles counts:
    a failed upload that later went through blocks nothing. again (owner, 6 Nov 2026: "submit every NOT DONE
    group, rejected ones too"): only a job still waiting on Myntra holds the group back."""
    have, mine = set(styles), [j for j in jobs if j["seller"] == seller]
    if any(j["status"] not in FINISHED and have & j["styles"] for j in mine):
        return "waiting on Myntra"
    if again:
        return ""
    same = [j for j in mine if j["styles"] == have]
    if same and same[-1]["status"] == "REJECTED":
        return "rejected, change the styles first"
    if same and same[-1]["status"] in ("FAILED", "PARTIAL_COMPLETE") and _recent(same[-1], today):
        return f"failed in the last {WAIT_DAYS} days"
    approved = set().union(*[j["styles"] for j in mine if j["status"] == "COMPLETED" and _recent(j, today)], set())
    if have <= approved:
        return "approved, site not updated yet"
    return ""


def group_state(jobs_newest_first: list[dict], pending: bool, today: date) -> str:
    """A group's state: the live check first, then its newest job."""
    if not pending:
        return DONE
    if not jobs_newest_first:
        return FRESH
    job = jobs_newest_first[0]
    if job["status"] == "COMPLETED":
        return APPROVED if _recent(job, today) else CHECK
    return {"PARTIAL_COMPLETE": PARTIAL, "FAILED": FAILED, "REJECTED": REJECTED}.get(job["status"], WAITING)


def changed_jobs(old: pd.DataFrame, new: pd.DataFrame) -> Counter:
    """New status -> jobs that are new or got that status since the old record."""
    was = dict(zip(old["JOB ID"].astype(str), old["JOB STATUS"].astype(str)))
    return Counter(str(s) for j, s in zip(new["JOB ID"].astype(str), new["JOB STATUS"].astype(str))
                   if j.isdigit() and was.get(j) != str(s))


def submit(folder: Path, record: pd.DataFrame, limit: int = 0, pause: float = 0.005,
           again: bool = False) -> tuple[pd.DataFrame, list[str], int, Counter]:
    """Upload the files of folder/ACC-<seller id>/; (record, problems, submitted, reason -> skipped).
    limit: at most that many groups in all (a test). again: see skip_reason."""
    from ..portals import myntra as mp
    from ..return_analysis.sources import env, myntra_portal
    rows, problems, skipped = [], [], Counter()
    jobs, today = jobs_of(record), date.today()
    for acc_dir in sorted(p for p in folder.iterdir() if p.is_dir() and p.name.startswith("ACC-")):
        seller = acc_dir.name[4:]
        account = ACCOUNT_OF.get(seller, seller)
        try:
            portal = myntra_portal(account)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{account}: no session ({str(exc)[:100]})")
            continue
        for f in sorted(acc_dir.glob("*.xlsx")):
            if limit and len(rows) >= limit:
                break
            uid, styles = template_rows(f)
            why = skip_reason(seller, styles, jobs, today, again)
            if why:
                skipped[why] += 1
                log.info("%s %s: %s: skipped", account, f.name, why)
                continue
            m = re.match(r"^(\d+)_(.+)_([^_]+)\.xlsx$", f.name)
            brand, article = (m.group(2), m.group(3)) if m else ("", "")
            try:
                job, status = str(portal.style_grouping_submit(f.name, f.read_bytes())), "SUBMITTED"
            except Exception as exc:  # noqa: BLE001 - one group never stops the others
                job, status = "", f"NOT SUBMITTED: {str(exc).splitlines()[0][:120]}"
                problems.append(f"{account} {f.name}: {status}")
            rows.append({"SUBMITTED ON": f"{datetime.now():%Y-%m-%d}", "TIME": f"{datetime.now():%H:%M}", "ACCOUNT": account,
                         "SELLER ID": seller, "UNIQUE ID": uid, "BRAND": brand, "ARTICLE TYPE": article, "FILE": f.name,
                         "STYLES": str(len(styles)), "STYLE IDS": ", ".join(styles), "JOB ID": job, "JOB STATUS": status,
                         "BY": "Ultron"})
            time.sleep(pause)
        mp.save_to_worker(env, portal.cookies(), account)
    if rows:
        record = pd.concat([record, pd.DataFrame(rows, columns=COLS)], ignore_index=True)
    return record, problems, sum(1 for r in rows if r["JOB ID"]), skipped


def _newest_first(record: pd.DataFrame) -> pd.DataFrame:
    return (record.assign(_job=pd.to_numeric(record["JOB ID"], errors="coerce"))
            .sort_values(["SUBMITTED ON", "_job"], ascending=False, na_position="last").drop(columns="_job"))


def write_record(record: pd.DataFrame, path: Path) -> Path:
    from .engine import format_workbook
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        _newest_first(record).to_excel(xw, sheet_name="SUBMISSIONS", index=False)
        format_workbook(xw.book)
    return path


def write_reasons(reasons: pd.DataFrame, path: Path) -> Path:
    from .engine import format_workbook
    rows = reasons.assign(_job=pd.to_numeric(reasons["JOB ID"], errors="coerce")).sort_values("_job", ascending=False, kind="stable").drop(columns="_job")
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        rows.to_excel(xw, sheet_name="REASONS", index=False)
        format_workbook(xw.book)
    return path


def apply(report: Path, record: pd.DataFrame, reasons: pd.DataFrame, today: date | None = None) -> dict[str, Counter]:
    """The account sheets in the owner's LAYOUT, a style not grouped yet with its own newest job and reason (every
    other row blank, and a style never uploaded), and the SUBMISSIONS sheet. Safe to run on a master that has them already. Returns seller ->
    pending groups per state."""
    from openpyxl import load_workbook
    from .engine import PENDING_REMARKS, REMARK_EXTRA, format_workbook
    today, states = today or date.today(), {}
    jobs = jobs_of(record)
    latest = {(j["seller"], s): j for j in jobs for s in j["styles"]}    # oldest first: the newest stays
    said = {(str(r["JOB ID"]), str(r["STYLE ID"])): str(r["REMARK"]) for _, r in reasons.iterrows()}
    wb = load_workbook(report)
    for old in [s for s in wb.worksheets if s.title.startswith("ACC-")]:
        seller = old.title[4:]
        rows = list(old.iter_rows(values_only=True))
        head = list(rows[0])
        groups: dict[str, dict] = {}
        out = []
        for values in rows[1:]:
            row = dict(zip(head, values))
            sid = str(row.get("Style ID") or "").replace(".0", "").strip()
            job = latest.get((seller, sid))
            remark = row.get("GROUPING REMARK")
            g = groups.setdefault(str(row.get("Unique ID")), {"styles": set(), "pending": False})
            g["pending"] |= remark in PENDING_REMARKS
            if remark != REMARK_EXTRA:      # a style to take out belongs to another group
                g["styles"].add(sid)
            row.update({"JOB ID": job["id"], "JOB STATUS": job["status"], "JOB SUBMITED DATE": job["day"],
                        "PORTAL REMARK": said.get((str(job["id"]), sid)) or job["remark"]} if job and remark in PENDING_REMARKS else
                       {"JOB ID": None, "JOB STATUS": None, "JOB SUBMITED DATE": None, "PORTAL REMARK": None})
            out.append([row.get(c) for c in LAYOUT])
        at, title = wb.index(old), old.title
        wb.remove(old)
        ws = wb.create_sheet(title, at)
        ws.append(LAYOUT)
        for values in out:
            ws.append(values)
        tally = Counter()
        for g in groups.values():
            if g["pending"]:
                mine = [j for j in reversed(jobs) if j["seller"] == seller and j["styles"] & g["styles"]]
                tally[group_state(mine, True, today)] += 1
        states[seller] = tally
    if "SUBMISSIONS" in wb.sheetnames:
        del wb["SUBMISSIONS"]
    ws = wb.create_sheet("SUBMISSIONS")
    ws.append(COLS)
    for r in _newest_first(record).itertuples(index=False):
        ws.append(["" if pd.isna(v) else v for v in r])
    format_workbook(wb)
    wb.save(report)
    return states


BRAND_MASTER = "MYNTRA GROUPING MASTER BRAND WISE.xlsx"


def brand_master(master: Path, dest: Path) -> Path:
    """The master brand-wise, one file (owner, 6 Nov 2026): a sheet per brand (only engine.BRANDS) with the rows
    of every account, ACCOUNT first and then the master's columns; a Summary per brand and account; and
    SUBMISSIONS with a BRANDS column (a job uploaded by hand gets the brands of its styles). Built from the
    finished account-wise master, so the job columns match it."""
    from openpyxl import Workbook, load_workbook
    from .engine import BRANDS, FILLS, format_workbook
    names = {b.strip().lower(): b for b in BRANDS}      # only the owner's brands, nothing else
    src = load_workbook(master, read_only=True)
    per_brand: dict[str, list] = {k: [] for k in names}
    head: list = []
    brand_of: dict[tuple[str, str], str] = {}           # (seller id, style id) -> brand
    for ws in src.worksheets:
        if not ws.title.startswith("ACC-"):
            continue
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        head = head or list(rows[0])
        col = {c: i for i, c in enumerate(rows[0])}
        seller = ws.title[4:]
        for values in rows[1:]:
            brand = str(values[col["Brand"]] or "").strip().lower()
            if brand in names:
                per_brand[brand].append([ACCOUNT_OF.get(seller, seller), *(values[col[c]] if c in col else None for c in head)])
                brand_of[(seller, str(values[col["Style ID"]] or "").replace(".0", "").strip())] = names[brand]
    record = list(src["SUBMISSIONS"].iter_rows(values_only=True)) if "SUBMISSIONS" in src.sheetnames else []
    src.close()

    wb = Workbook()
    wb.remove(wb.active)
    summary = []
    at = head.index("GROUPING REMARK") + 1 if head else None
    uid_at = head.index("Unique ID") + 1 if head else None
    for key, rows in per_brand.items():
        if not rows:
            continue
        ws = wb.create_sheet(names[key][:31])
        ws.append(["ACCOUNT", *head])
        for values in rows:
            ws.append(values)
        for account in dict.fromkeys(r[0] for r in rows):
            mine = [r for r in rows if r[0] == account]
            remarks = Counter(r[at] for r in mine)
            summary.append([names[key], account, len({r[uid_at] for r in mine}), len(mine), *(remarks.get(k, 0) for k in FILLS)])
    ws = wb.create_sheet("Summary")
    ws.append(["Brand", "Account", "Groups", "Rows", *FILLS])
    for values in summary:
        ws.append(values)
    ws = wb.create_sheet("SUBMISSIONS")
    if record:
        col = {c: i for i, c in enumerate(record[0])}
        ws.append(["BRANDS", *record[0]])
        for values in record[1:]:
            named = str(values[col["BRAND"]] or "").strip() if "BRAND" in col else ""
            seller = str(values[col["SELLER ID"]] or "").strip() if "SELLER ID" in col else ""
            styles = [x.strip() for x in str(values[col["STYLE IDS"]] or "").split(",")] if "STYLE IDS" in col else []
            brands = [named] if named else sorted({brand_of[(seller, x)] for x in styles if (seller, x) in brand_of})
            ws.append([", ".join(brands), *values])
    format_workbook(wb)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / BRAND_MASTER
    wb.save(path)
    return path


def state_line(tally: Counter) -> str:
    """The pending groups of one account, per state, for Telegram."""
    return " · ".join(f"{s} {tally[s]}" for s in (FRESH, WAITING, APPROVED, CHECK, PARTIAL, FAILED, REJECTED) if tally[s]) or "none pending"
