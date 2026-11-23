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

from ..portals.myntra import ACCOUNTS as MYNTRA_ACCOUNTS  # the one account list
import io
import logging
import re
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from ultron.core import http
from ..core.tables import clean_id

log = logging.getLogger("bindal.myntra_grouping")

RECORD = "GROUPING SUBMISSIONS.xlsx"
COLS = ["SUBMITTED ON", "TIME", "ACCOUNT", "SELLER ID", "UNIQUE ID", "BRAND", "ARTICLE TYPE", "FILE", "STYLES",
        "STYLE IDS", "JOB ID", "JOB STATUS", "TOTAL RECORDS", "PROCESSED RECORDS", "ERRED RECORDS", "BY", "PORTAL REMARK"]
SELLER_OF = {acc: str(pid) for acc, pid in MYNTRA_ACCOUNTS.items()}
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


TEXT = {c: pl.Utf8 for c in COLS}


def _text_table(df: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    """The columns of a record sheet as text, in this order (a column the sheet lacks is empty)."""
    return df.select(*[(pl.col(c).cast(pl.Utf8) if c in df.columns else pl.lit(None, dtype=pl.Utf8)).alias(c) for c in cols])


def read_record(path: Path | None) -> pl.DataFrame:
    from ..core.tables import read_excel_text
    if path and path.exists():
        return _text_table(read_excel_text(path, "SUBMISSIONS"), COLS)
    return pl.DataFrame(schema=TEXT)


def _upload_styles(data) -> tuple[str, list[str]]:
    """(unique id, style ids) of an upload file (a path or its bytes): A2, and column C."""
    from ..core.tables import read_excel_text
    df = read_excel_text(data, 0)
    if not df.height or df.width < 3:
        return "", []
    uid = str(df[0, 0]).strip() if df[0, 0] is not None else "nan"
    return uid, [clean_id(x) for x in df[:, 2].drop_nulls().to_list()]


def template_rows(path: Path) -> tuple[str, list[str]]:
    """(unique id, style ids) of one upload file."""
    return _upload_styles(path)


def _when(value) -> tuple[str, str]:
    """(date, time) in IST of a job's createdAt (the portal answers UTC, ISO text or epoch ms)."""
    try:
        text = str(value)
        if text.isdigit():
            t = datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc).replace(tzinfo=None)
        else:
            t = datetime.fromisoformat(text.replace("Z", "+00:00"))
            t = t.astimezone(timezone.utc).replace(tzinfo=None) if t.tzinfo else t
        t = t + timedelta(hours=5, minutes=30)
        return f"{t:%Y-%m-%d}", f"{t:%H:%M}"
    except (ValueError, TypeError, OverflowError):
        return str(value)[:10], ""


def _job_styles(job: dict) -> tuple[str, list[str]]:
    """(unique id, style ids) from a job's input file; empty when it cannot be read."""
    url = (job.get("metaData") or {}).get("signedInputFilePath")
    if not url:
        return "", []
    try:
        r = http.get(url, timeout=60)
        r.raise_for_status()
        return _upload_styles(r.content)
    except Exception as exc:  # noqa: BLE001 - the job is still recorded
        log.info("Input file of job %s not read: %s", job.get("id"), str(exc)[:100])
        return "", []


def _add(record: pl.DataFrame, rows: list[dict]) -> pl.DataFrame:
    """New rows at the end of the record (their missing columns empty)."""
    if not rows:
        return record
    new = pl.DataFrame([{c: r.get(c) for c in COLS} for r in rows], schema=TEXT)
    return pl.concat([record, new], how="vertical")


def sync_jobs(record: pl.DataFrame, accounts: list[str] | None = None) -> tuple[pl.DataFrame, list[str]]:
    """The portal's jobs into the record, every status read again; problems, one line each."""
    from ..portals import myntra as mp
    from ..return_analysis.sources import env, myntra_portal
    problems, new, seen = [], [], {}
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
        known = set(record["JOB ID"].fill_null("nan").to_list())
        for j in jobs:
            jid = str(j.get("id"))
            counts = [str(j.get("status") or ""), str(j.get("totalRecords") or 0), str(j.get("processedRecords") or 0),
                      str(j.get("erredRecords") or 0)]
            day, at = _when(j.get("createdAt"))
            if jid in known:     # the portal's own time: the clock of the run that uploaded can be UTC
                seen[jid] = {"JOB ID": jid, "SUBMITTED ON": day, "TIME": at, "JOB STATUS": counts[0], "TOTAL RECORDS": counts[1],
                             "PROCESSED RECORDS": counts[2], "ERRED RECORDS": counts[3]}
                continue
            uid, styles = _job_styles(j)
            new.append({"SUBMITTED ON": day, "TIME": at, "ACCOUNT": account, "SELLER ID": SELLER_OF[account],
                        "UNIQUE ID": uid, "BRAND": "", "ARTICLE TYPE": "", "FILE": "", "STYLES": str(len(styles)),
                        "STYLE IDS": ", ".join(styles), "JOB ID": jid, "JOB STATUS": counts[0], "TOTAL RECORDS": counts[1],
                        "PROCESSED RECORDS": counts[2], "ERRED RECORDS": counts[3], "BY": "Portal"})
    if seen:
        fresh = pl.DataFrame(list(seen.values()), schema={c: pl.Utf8 for c in next(iter(seen.values()))})
        record = record.update(fresh, on="JOB ID", how="left")
    return _add(record, new), problems


def read_reasons(path: Path | None) -> pl.DataFrame:
    from ..core.tables import read_excel_text
    if path and path.exists():
        return _text_table(read_excel_text(path, "REASONS"), REASON_COLS)
    return pl.DataFrame(schema={c: pl.Utf8 for c in REASON_COLS})


def _report_rows(link: str) -> list[dict]:
    """The rows of one job's result report. Its columns differ: Unique ID, Style ID, Grouping Type, Remarks,
    GroupId; a rejected job's uniqueId, styleId, groupingType, rejectReason. A long report repeats its header.
    When the portal could not read the upload at all, its error stands alone in the first column."""
    import zipfile

    from ..core.tables import read_text_csv
    z = zipfile.ZipFile(io.BytesIO(http.get(link, timeout=60).content))
    df = read_text_csv(z.open(z.namelist()[0]).read(), na_words=True)
    df = df.rename({c: re.sub(r"[^a-z]", "", str(c).lower()) for c in df.columns}).fill_null("")
    out = []
    for r in df.iter_rows(named=True):
        style = clean_id(r.get("styleid", ""))
        remark = str(r.get("remarks", r.get("rejectreason", ""))).strip()
        unique = str(r.get("uniqueid", "")).strip()
        if style.lower().replace(" ", "") == "styleid":
            continue
        if not style and not remark and "exception" in unique.lower():
            remark, unique = unique.rsplit("Exception:", 1)[-1].strip(), ""
        if not (style or remark):
            continue
        out.append({"UNIQUE ID": unique, "STYLE ID": style, "GROUPING TYPE": str(r.get("groupingtype", "")).strip(),
                    "REMARK": remark, "GROUP ID": clean_id(r.get("groupid", ""))})
    return out


def update_reasons(record: pl.DataFrame, reasons: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, list[str]]:
    """Every finished job's report not read yet into the reasons, JOB STATUS brought up to date, and PORTAL REMARK
    of each job from them; (record, reasons, problems). A report that cannot be read is tried again next run."""
    from ..return_analysis.sources import myntra_portal
    portals, new, unread = {}, [], 0
    have = set(reasons["JOB ID"].fill_null("nan").to_list())
    done = record.filter(pl.col("JOB ID").str.contains(r"^\d+$").fill_null(False) & pl.col("JOB STATUS").is_in(sorted(FINISHED)))
    for r in done.iter_rows(named=True):
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
        reasons = pl.concat([reasons, pl.DataFrame([{c: n.get(c) for c in REASON_COLS} for n in new],
                                                   schema={c: pl.Utf8 for c in REASON_COLS})], how="vertical")
    status = record.select(pl.col("JOB ID").fill_null("nan").alias("_j"), pl.col("JOB STATUS").alias("_s")).unique("_j", keep="last")
    reasons = (reasons.with_columns(pl.col("JOB ID").fill_null("nan").alias("_j")).drop("JOB STATUS")
                      .join(status, on="_j", how="left", maintain_order="left")
                      .rename({"_s": "JOB STATUS"}).drop("_j").select(REASON_COLS))
    said = reasons.filter(~pl.col("REMARK").fill_null("nan").str.to_uppercase().is_in(["SUCCESS", "", "NAN"]))
    joined = (said.group_by(pl.col("JOB ID").fill_null("nan").alias("_j"), maintain_order=True)
                  .agg(pl.col("REMARK").unique(maintain_order=True).str.join(" | ").str.slice(0, 300).alias("_r")))
    record = (record.with_columns(pl.col("JOB ID").fill_null("nan").alias("_j")).join(joined, on="_j", how="left", maintain_order="left")
                    .with_columns(pl.col("_r").fill_null("").alias("PORTAL REMARK")).select(COLS))
    return record, reasons, [f"{unread} job reports not read: tried again next run"] if unread else []


def jobs_of(record: pl.DataFrame) -> list[dict]:
    """Every job the portal took, oldest first (by job id: the portal numbers them in order)."""
    out = []
    for r in record.iter_rows(named=True):
        jid = clean_id(r["JOB ID"])
        if not jid.isdigit():
            continue
        out.append({"id": int(jid), "seller": str(r["SELLER ID"]), "day": str(r["SUBMITTED ON"])[:10], "status": str(r["JOB STATUS"]),
                    "styles": {s for s in str(r["STYLE IDS"]).split(", ") if s and s not in ("nan", "None")},
                    "remark": r["PORTAL REMARK"] or ""})
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


def changed_jobs(old: pl.DataFrame, new: pl.DataFrame) -> Counter:
    """New status -> jobs that are new or got that status since the old record."""
    was = dict(zip(old["JOB ID"].fill_null("nan").to_list(), old["JOB STATUS"].fill_null("nan").to_list()))
    return Counter(s for j, s in zip(new["JOB ID"].fill_null("nan").to_list(), new["JOB STATUS"].fill_null("nan").to_list())
                   if j.isdigit() and was.get(j) != s)


def submit(folder: Path, record: pl.DataFrame, limit: int = 0, pause: float = 0.005,
           again: bool = False) -> tuple[pl.DataFrame, list[str], int, Counter]:
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
    return _add(record, rows), problems, sum(1 for r in rows if r["JOB ID"]), skipped


def _newest_first(record: pl.DataFrame) -> pl.DataFrame:
    job = pl.col("JOB ID").str.strip_chars().cast(pl.Float64, strict=False)
    return (record.with_columns(job.alias("_job"))
                  .sort(["SUBMITTED ON", "_job"], descending=True, nulls_last=True, maintain_order=True).drop("_job"))


def write_record(record: pl.DataFrame, path: Path) -> Path:
    from .engine import write_tables
    write_tables(path, [("SUBMISSIONS", COLS, _newest_first(record).rows())])
    return path


def write_reasons(reasons: pl.DataFrame, path: Path) -> Path:
    from .engine import write_tables
    job = pl.col("JOB ID").str.strip_chars().cast(pl.Float64, strict=False)
    rows = reasons.with_columns(job.alias("_job")).sort("_job", descending=True, nulls_last=True, maintain_order=True).drop("_job")
    write_tables(path, [("REASONS", REASON_COLS, rows.select(REASON_COLS).rows())])
    return path


def read_sheets(path: Path) -> dict[str, pl.DataFrame]:
    """Every sheet of a workbook, typed (pl.read_excel, calamine)."""
    return pl.read_excel(path, sheet_id=0, engine="calamine", raise_if_empty=False)


def apply(report: Path, record: pl.DataFrame, reasons: pl.DataFrame, today: date | None = None) -> dict[str, Counter]:
    """The master written again (xlsxwriter): the account sheets in the owner's LAYOUT, a style not grouped yet with its own
    newest job and reason (every other row blank, and a style never uploaded), the other sheets as they were, and the
    SUBMISSIONS sheet. Safe to run on a master that has them already. Returns seller -> pending groups per state."""
    from .engine import PENDING_REMARKS, REMARK_EXTRA, write_tables
    today, states = today or date.today(), {}
    jobs = jobs_of(record)
    latest = {(j["seller"], s): j for j in jobs for s in j["styles"]}    # oldest first: the newest stays
    said = {(str(j), str(s)): str(r) for j, s, r in reasons.select("JOB ID", "STYLE ID", "REMARK").iter_rows()}
    out_sheets = []
    for title, sheet in read_sheets(report).items():
        if title == "SUBMISSIONS":
            continue
        if not title.startswith("ACC-"):
            out_sheets.append((title, sheet.columns, sheet.rows()))
            continue
        seller = title[4:]
        groups: dict[str, dict] = {}
        out = []
        for row in sheet.iter_rows(named=True):
            sid = clean_id(row.get("Style ID") or "")
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
        out_sheets.append((title, LAYOUT, out))
        tally = Counter()
        for g in groups.values():
            if g["pending"]:
                mine = [j for j in reversed(jobs) if j["seller"] == seller and j["styles"] & g["styles"]]
                tally[group_state(mine, True, today)] += 1
        states[seller] = tally
    out_sheets.append(("SUBMISSIONS", COLS, _newest_first(record).rows()))
    write_tables(report, out_sheets)
    return states


BRAND_MASTER = "MYNTRA GROUPING MASTER BRAND WISE.xlsx"


def brand_master(master: Path, dest: Path) -> Path:
    """The master brand-wise, one file (owner, 6 Nov 2026): a sheet per brand (only engine.BRANDS) with the rows
    of every account, ACCOUNT first and then the master's columns; a Summary per brand and account; and
    SUBMISSIONS with a BRANDS column (a job uploaded by hand gets the brands of its styles). Built from the
    finished account-wise master, so the job columns match it."""
    from .engine import BRANDS, FILLS, write_tables
    names = {b.strip().lower(): b for b in BRANDS}      # only the owner's brands, nothing else
    per_brand: dict[str, list] = {k: [] for k in names}
    head: list = []
    brand_of: dict[tuple[str, str], str] = {}           # (seller id, style id) -> brand
    book = read_sheets(master)
    for title, sheet in book.items():
        if not title.startswith("ACC-") or not sheet.width:
            continue
        head = head or list(sheet.columns)
        seller = title[4:]
        for row in sheet.iter_rows(named=True):
            brand = str(row.get("Brand") or "").strip().lower()
            if brand in names:
                per_brand[brand].append([ACCOUNT_OF.get(seller, seller), *(row.get(c) for c in head)])
                brand_of[(seller, clean_id(row.get("Style ID") or ""))] = names[brand]
    record = book.get("SUBMISSIONS")

    sheets, summary = [], []
    at = head.index("GROUPING REMARK") + 1 if head else None
    uid_at = head.index("Unique ID") + 1 if head else None
    for key, rows in per_brand.items():
        if not rows:
            continue
        sheets.append((names[key][:31], ["ACCOUNT", *head], rows))
        for account in dict.fromkeys(r[0] for r in rows):
            mine = [r for r in rows if r[0] == account]
            remarks = Counter(r[at] for r in mine)
            summary.append([names[key], account, len({r[uid_at] for r in mine}), len(mine), *(remarks.get(k, 0) for k in FILLS)])
    sheets.append(("Summary", ["Brand", "Account", "Groups", "Rows", *FILLS], summary))
    if record is not None and record.width:
        out = []
        for r in record.iter_rows(named=True):
            named = str(r.get("BRAND") or "").strip()
            seller = str(r.get("SELLER ID") or "").strip()
            styles = [x.strip() for x in str(r.get("STYLE IDS") or "").split(",")]
            brands = [named] if named else sorted({brand_of[(seller, x)] for x in styles if (seller, x) in brand_of})
            out.append([", ".join(brands), *(v for v in r.values())])
        sheets.append(("SUBMISSIONS", ["BRANDS", *record.columns], out))
    else:
        sheets.append(("SUBMISSIONS", [], []))
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / BRAND_MASTER
    write_tables(path, sheets)
    return path


def state_line(tally: Counter) -> str:
    """The pending groups of one account, per state, for Telegram."""
    return " · ".join(f"{s} {tally[s]}" for s in (FRESH, WAITING, APPROVED, CHECK, PARTIAL, FAILED, REJECTED) if tally[s]) or "none pending"
