# Project context — BINDAL EXPORTS report bots

<!-- AUTO:synced -->Last synced with the code: 2026-11-01.<!-- /AUTO:synced -->
Owner: Bhikan (GitHub `bindalbhikan`, commit author
`bhikan.serein@gmail.com`). Every bot reports to Telegram **@bindal_exports_bot**.

This folder is the working copy of the GitHub repo **`bindalbhikan/Ultron`** (public since
2026-10-18). Read next: **`docs/ARCHITECTURE.md`** (how it fits together + the checklist for a new
working), **`docs/PORTALS.md`** (every outside system, its API and limits), **`docs/bots/<bot>.md`**
(one page per working). `README.md` is the short user guide. Every agent starts with
**`AGENTS.md`** (rules + how the docs stay up to date).

## The workings

Generated from `run.py`, the workflows, the work schedule (`TASKS`) and `docs/bots/` by
`python scripts/docs/sync_docs.py` (see `AGENTS.md`); do not edit inside the block.

<!-- AUTO:workings -->
| Bot | Run | What it does | Workflow | When (IST) | Page |
|---|---|---|---|---|---|
| agent-chat | `python run.py agent-chat` | Agent chat | `agent-chat.yml` Agent chat | on a plain-text Telegram message from an allowed chat | `docs/bots/agent-chat.md` |
| agent-watch | `python run.py agent-watch` | Agent watch | `agent-watch.yml` Agent watch | as every bot workflow finishes | `docs/bots/agent-watch.md` |
| ajio-ads | `python run.py ajio-ads` | AJIO ads / TOT gap | `ajio-ads.yml` AJIO ads TOT gap | 9:00 AM monthly (3rd); 9:00 AM monthly (5th) | `docs/bots/ajio-ads.md` |
| ajio-spf | `python run.py ajio-spf` | AJIO SPF | `ajio-spf.yml` AJIO SPF run | 9:00 AM weekly (wed, sat); 9:00 AM daily (not wed, sat) | `docs/bots/ajio-spf.md` |
| ajio-tat | `python run.py ajio-tat` | AJIO dispatch TAT | `ajio-tat.yml` AJIO TAT daily update | 5:30 PM daily | `docs/bots/ajio-tat.md` |
| deadstock | `python run.py deadstock` | Dead stock report | `deadstock.yml` Dead stock report | 11:00 AM monthly (1st) | `docs/bots/deadstock.md` |
| evening | `python run.py evening` | Evening summary | `evening.yml` Evening summary | 8:00 PM daily | `docs/bots/evening.md` |
| flipkart-tat | `python run.py flipkart-tat` | Flipkart TAT | `flipkart-tat.yml` Flipkart TAT daily update | 6:00 PM daily | `docs/bots/flipkart-tat.md` |
| inv-push | `python run.py inv-push` | OMSGuru inventory push | `inv-push.yml` OMSGuru inventory push | every 3 hours, 6 AM - 3 AM daily (8 times) | `docs/bots/inv-push.md` |
| labels | `python run.py labels` | Label check | `labels.yml` Label check | 6:00 PM daily | `docs/bots/labels.md` |
| listings | `python run.py listings` | Listing health | `listings.yml` Listing health | 11:30 AM daily | `docs/bots/listings.md` |
| mis | `python run.py mis` | Monthly MIS | `mis.yml` Monthly MIS | 11:00 AM monthly (2nd) | `docs/bots/mis.md` |
| morning | `python run.py morning` | Morning report | `morning.yml` Morning report | 9:30 AM daily | `docs/bots/morning.md` |
| myntra-history | `python run.py myntra-history` | Myntra order + return history | `myntra-history.yml` Myntra order + return history | by hand only | `docs/bots/myntra-history.md` |
| myntra-otp | `python run.py myntra-otp` | Myntra courier OTP | `myntra-otp.yml` Myntra courier OTP | 11:00 AM daily; 11:45 AM daily | `docs/bots/myntra-otp.md` |
| myntra-reports | `python run.py myntra-reports` | Myntra daily reports | `myntra-reports.yml` Myntra daily reports | 10:00 AM daily | `docs/bots/myntra-reports.md` |
| myntra-spf | `python run.py myntra-spf` | Myntra SPF master | `myntra-spf.yml` Myntra SPF master | 7:00 AM daily; 9:00 AM daily | `docs/bots/myntra-spf.md` |
| myntra-tat | `python run.py myntra-tat` | Myntra courier scorecard | `myntra-tat.yml` Myntra courier scorecard | 6:30 PM daily | `docs/bots/myntra-tat.md` |
| myntra-zero-td | `python run.py myntra-zero-td` | Myntra zero TD | `myntra-zero-td.yml` Myntra zero TD | 7:00 AM mon-sat; 9:00 AM mon-sat; 10:00 AM daily; 11:00 AM mon-sat; 1:00 PM mon-sat; 3:00 PM mon-sat; 5:00 PM mon-sat; 7:00 PM mon-sat | `docs/bots/myntra-zero-td.md` |
| returns | `python run.py returns` | Return analysis (monthly + yearly) | `returns.yml` Return analysis | 7:00 AM monthly (15th); 2:00 PM monthly (15th) | `docs/bots/returns.md` |
| sale | `python run.py sale` | Daily sale | `sale.yml` Daily sale report | 7:00 AM daily; 3:30 PM daily | `docs/bots/sale.md` |
| sla | `python run.py sla` | SLA warning | `sla.yml` SLA warning | 12:00 PM daily; 3:00 PM daily | `docs/bots/sla.md` |
| stock | `python run.py stock` | Stock-out alert | `stock.yml` Stock-out alert | 10:00 AM daily | `docs/bots/stock.md` |
| vms | `python run.py vms` | Myntra VMS | `vms.yml` Myntra VMS report | 5:30 PM daily | `docs/bots/vms.md` |
| weekly | `python run.py weekly` | Weekly review | `weekly.yml` Weekly review | 10:15 AM weekly (mon) | `docs/bots/weekly.md` |
| work-schedule | `python run.py work-schedule` | Agent work schedule | `agent-watch.yml` Agent watch | after every bot run | `docs/bots/work-schedule.md` |
<!-- /AUTO:workings -->

Gaps the sync found:

<!-- AUTO:gaps -->
- none: every bot has its page and its workflow is watched
<!-- /AUTO:gaps -->

## The agent's folder: Drive `BINDAL EXPORTS/AGENT WORK`

Everything the agent works on lives here, kept by portal, the daily reports together (since 29 Oct 2026; moved, so every file
and folder kept its Drive id):

```
AGENT WORK/
  AGENT REPORT WORK SCHEDULE REPORT.xlsx   the agent's reporting sheet (below)
  AGENT LOGS/<OCT-26>/<29-10-26>/          every run's hyper log
  MYNTRA/   MYNTRA DAILY REPORTS/, MYNTRA DAILY RETURN DELIVERY REPORT.xlsx, MYNTRA ZERO TD UPDATE SHEET.xlsx,
            MYNTRA ZERO TD SHEETS/, MYNTRA SIZE CHART WORKING/, MYNTRA ORDER RETURN REPORTS .../
  AJIO/     Ajio Daily Order Tat Check Working/ (TAT master), Ajio Ads Gap Working/
  DAILY REPORTING/   DAILY SALE REPORT BINDAL/ (SALE REPORT.xlsx), VMS/ (the daily reports in one place)
  PORTAL REPORTS/    <MYNTRA|AJIO|FLIPKART>/<YYYY>/<Mon-YY>/Sale Report <Mon-YY>/, Return Report <Mon-YY>/
                     every portal's monthly sale + return reports, one calendar month each (1st to last day),
                     saved by the return analysis on the 15th; the business reporting reads them
                     (core/portal_reports.py). A file named ... PARTIAL misses days (its source had gaps)
  BUSINESS REPORTING/ the owner's Myntra sale / return / payment analysis (CONTEXT.md and scripts in it)
```

A bot that finds its file by name looks in its portal's folder (`AREA = "MYNTRA"` in the Myntra
workings); the others use Drive ids (`SALE_DRIVE_FILE_ID`, `VMS_DRIVE_FILE_ID`,
`TAT_DRIVE_FOLDER_ID`, `AJIO_ADS_FOLDER_ID`). New agent work goes into the portal's folder.

## The agent's reporting sheet

**`AGENT WORK/AGENT REPORT WORK SCHEDULE REPORT.xlsx`** on Drive is the agent's reporting sheet:
every scheduled task (SR / TASK NAME / TIME / DAILY/WEEKLY / WORK) and, one sheet a month, a box
per day ticked ☑ once that task's run succeeded (red = missed). It is rebuilt from the GitHub run
history after every bot run (`python run.py work-schedule`, `docs/bots/work-schedule.md`). A new
scheduled task, or a new daily step of a working, goes into `TASKS` / `WORK` in
`src/ultron/workings/work_schedule/pipeline.py` as well as the worker's `SCHEDULE`. Every bot run's
detailed **hyper log** is kept on Drive in `AGENT WORK/AGENT LOGS/<month>/<date>/`
(`core/hyperlog.py`), not in this sheet.

## Rules every working keeps

- **Data must never be wrong.** A source that fails, or a month whose source data is incomplete
  (e.g. Flipkart returns older than ~4 months), is left out and named — never shown as zero.
- A blank value never erases an existing cell; one row per order / day; old data is kept. A run
  whose required source returns nothing at all leaves the workbook untouched.
- Inputs come from the portals; a report already generated for the same dates is reused; an old
  one that will not download is asked for again, waited for, and the run carries on.
- Return received (Myntra and AJIO SPF): ERP GRN first, then OMSGuru (only rows whose final status
  is blank), then the manual sheet.
- A hand-run tool brought into the bot stays unchanged (`engine.py`); its port is checked file by
  file against the tool's own output.
- SPF: per-run caps; any failed source turns the run into a dry run; a failed "ticket already
  exists?" check skips that ticket. AJIO tickets / replies only Wed + Sat.
- Myntra: never bypass its reCAPTCHA; never log out of the portal (it ends the bot's session).

## Settings and secrets — never in git

- **Public repo**: every workflow runs its bot through `scripts/github/ci_run.sh` (public log = exit code
  only; log + `output/` uploaded AES-encrypted with `ARTIFACT_KEY`; read with
  `python scripts/github/run_output.py <run id>`). Never commit or print logins, cookies or customer data;
  folder / file ids and chat ids live in secrets.
- Local: one `.env` (copy of `.env.example`) + `service_account.json` (Google service account
  `ajio-tat-bot@storied-port-441507-k7.iam.gserviceaccount.com`, Editor on the folders). Ignored by
  git, as are `output/`, workbooks, CSVs, captures, `myntra_session*.json`, `scripts/*.txt`.
- GitHub: repository **Secrets** (logins, Drive ids, `GOOGLE_SERVICE_ACCOUNT_JSON`,
  `GOOGLE_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN`, `ARTIFACT_KEY`) and **Variables** (tuning). `SPF_DRY_RUN=0` = AJIO SPF
  posts for real. A blank GitHub variable arrives as an empty string and falls back to the default.
- Cloudflare worker secrets: see `docs/bots/worker-and-dashboard.md`.
- New Drive files need the owner's OAuth token (the service account cannot create files): `docs/PORTALS.md`.

## Hand-run tools the workings came from (still in their Drive folders)

`RETURN ANALYSIS/main.py` → returns · `SPF/MYNTRA/main.py` → myntra-spf · `SPF/AJIO/main.py` →
ajio-spf (`master_engine.py`) · `AGENT WORK/AJIO/Ajio Ads Gap Working/main.py` → ajio-ads.
