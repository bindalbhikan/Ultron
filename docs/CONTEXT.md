# Project context — BINDAL EXPORTS report bots

<!-- AUTO:synced -->Last synced with the code: 2026-11-25.<!-- /AUTO:synced -->
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
| ajio-tat | `python run.py ajio-tat` | AJIO dispatch TAT | `ajio-tat.yml` AJIO TAT daily update | 6:00 PM daily | `docs/bots/ajio-tat.md` |
| business-report | `python run.py business-report` | Business reporting | `business-report.yml` Business reporting | after every `portal-reports` run | `docs/bots/business-report.md` |
| deadstock | `python run.py deadstock` | Dead stock report | `deadstock.yml` Dead stock report | 11:00 AM monthly (1st) | `docs/bots/deadstock.md` |
| erp-oms-return | `python run.py erp-oms-return` | ERP to OMSGuru returns | `erp-oms-return.yml` ERP to OMSGuru returns | 8:00 PM daily | `docs/bots/erp-oms-return.md` |
| evening | `python run.py evening` | Evening summary | `evening.yml` Evening summary | 8:00 PM daily | `docs/bots/evening.md` |
| flipkart-calc | `python run.py flipkart-calc` | Flipkart calculator | `flipkart-calc.yml` Flipkart calculator | 7:00 AM weekly (mon) | `docs/bots/flipkart-calc.md` |
| flipkart-listing-file | `python run.py flipkart-listing-file` | Flipkart listing file | `flipkart-listing-file.yml` Flipkart listing file | 11:00 AM daily | `docs/bots/flipkart-listing-file.md` |
| flipkart-price | `python run.py flipkart-price` | Flipkart Final TP update | `flipkart-price.yml` Flipkart Final TP update | 8:00 AM daily | `docs/bots/flipkart-price.md` |
| flipkart-tat | `python run.py flipkart-tat` | Flipkart TAT | `flipkart-tat.yml` Flipkart TAT daily update | 6:00 PM daily | `docs/bots/flipkart-tat.md` |
| inv-push | `python run.py inv-push` | OMSGuru inventory push | `inv-push.yml` OMSGuru inventory push | every 3 hours, 6 AM - 3 AM daily (8 times) | `docs/bots/inv-push.md` |
| labels | `python run.py labels` | Label check | `labels.yml` Label check | 6:00 PM daily | `docs/bots/labels.md` |
| listings | `python run.py listings` | Listing health | `listings.yml` Listing health | 11:30 AM daily | `docs/bots/listings.md` |
| master-sheet | `python run.py master-sheet` | MasterSheet | `master-sheet.yml` MasterSheet from OMSGuru | 1:00 AM daily | `docs/bots/master-sheet.md` |
| mis | `python run.py mis` | Monthly MIS | `mis.yml` Monthly MIS | 11:00 AM monthly (2nd) | `docs/bots/mis.md` |
| morning | `python run.py morning` | Morning report | `morning.yml` Morning report | 9:30 AM daily | `docs/bots/morning.md` |
| myntra-grouping | `python run.py myntra-grouping` | Myntra colour grouping | `myntra-grouping.yml` Myntra colour grouping | 12:00 PM every 3 days; 8:00 PM daily | `docs/bots/myntra-grouping.md` |
| myntra-history | `python run.py myntra-history` | Myntra order + return history | `myntra-history.yml` Myntra order + return history | by hand only: Menu > Myntra > Order + return history | `docs/bots/myntra-history.md` |
| myntra-otp | `python run.py myntra-otp` | Myntra courier OTP | `myntra-otp.yml` Myntra courier OTP | 11:00 AM daily; 11:40 AM daily | `docs/bots/myntra-otp.md` |
| myntra-reports | `python run.py myntra-reports` | Myntra daily reports | `myntra-reports.yml` Myntra daily reports | 9:30 AM daily | `docs/bots/myntra-reports.md` |
| myntra-spf | `python run.py myntra-spf` | Myntra SPF master | `myntra-spf.yml` Myntra SPF master | 10:00 AM daily | `docs/bots/myntra-spf.md` |
| myntra-tat | `python run.py myntra-tat` | Myntra courier scorecard | `myntra-tat.yml` Myntra courier scorecard | 6:30 PM daily | `docs/bots/myntra-tat.md` |
| myntra-zero-td | `python run.py myntra-zero-td` | Myntra zero TD | `myntra-zero-td.yml` Myntra zero TD | 7:00 AM mon-sat; 9:00 AM mon-sat; 10:00 AM daily; 11:00 AM mon-sat; 1:00 PM mon-sat; 3:00 PM mon-sat; 5:00 PM mon-sat; 7:00 PM mon-sat | `docs/bots/myntra-zero-td.md` |
| portal-reports | `python run.py portal-reports` | Portal reports | `portal-reports.yml` Portal reports | 11:00 AM monthly (2nd); 11:00 AM monthly (15th) | `docs/bots/portal-reports.md` |
| portal-sale | `python run.py portal-sale` | Portal sale report (real sale) | `portal-sale.yml` Portal sale report | 5:30 PM daily | `docs/bots/portal-sale.md` |
| returns | `python run.py returns` | Return analysis (monthly + yearly) | `returns.yml` Return analysis | 7:00 AM monthly (15th); 7:00 AM monthly (10th); 2:00 PM monthly (10th); 2:00 PM monthly (15th) | `docs/bots/returns.md` |
| sale | `python run.py sale` | Daily sale | `sale.yml` Daily sale report | 3:30 PM daily | `docs/bots/sale.md` |
| sla | `python run.py sla` | SLA warning | `sla.yml` SLA warning | 12:00 PM daily; 3:00 PM daily | `docs/bots/sla.md` |
| stock | `python run.py stock` | Stock-out alert | `stock.yml` Stock-out alert | 10:00 AM daily | `docs/bots/stock.md` |
| ticket-followup | `python run.py ticket-followup` | Ticket follow-up | `ticket-followup.yml` Ticket follow-up | 8:00 PM daily | `docs/bots/ticket-followup.md` |
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
  MYNTRA/   MYNTRA DAILY REPORTS/ (up to 15 Nov 2026 only), MYNTRA DAILY RETURN DELIVERY REPORT.xlsx,
            MYNTRA ZERO TD SHEETS/ (MYNTRA ZERO TD UPDATE SHEET.xlsx = the styles to check, MYNTRA ZERO TD MASTER.xlsx =
            times at MRP per style / day / month, <MON-YY>/<dd-mm-yy>/ every check), MYNTRA SIZE CHART WORKING/, MYNTRA ORDER RETURN REPORTS .../
  AJIO/     Ajio Daily Order Tat Check Working/ (TAT master), Ajio Ads Gap Working/
  DAILY REPORTING/   DAILY SALE REPORT BINDAL/ (SALE REPORT.xlsx, PORTAL SALE REPORT.xlsx), VMS/ (the daily reports in one place)
  PORTAL REPORTS/    <MYNTRA|AJIO|FLIPKART>/<YYYY>/<Mon-YY>/<PORTAL> [<ACCOUNT>] ORDER|RETURN|PAYMENT REPORT <MON-YY>
                     every portal's monthly reports, one calendar month each, no sub folders (the name says
                     what it is; PARTIAL = days missing): order + payment reports on the 2nd (portal-reports, made anew on the 15th),
                     return reports by the return analysis on the 10th (replaced by the 15th's fresh second
                     try); the business reporting reads them (core/portal_reports.py)
  BUSINESS REPORTING/ the owner's Myntra sale / return / payment analysis (CONTEXT.md and scripts in it)
  MASTER SHEET/      MasterSheet.xlsx, the one SKU master every working and the chat agent read (core/master_sheet.py): MasterData rebuilt
                     from OMSGuru at 1 AM (master-sheet), REMOVED LISTINGS, the owner's Master Sku / Fabric Code /
                     Launch Date & Size Count (owner, 24 Nov 2026; the old copies in BUSINESS REPORTING and RETURN
                     ANALYSIS/Supporting are no longer read)
  SPF CLAIMS/        the final SPF master sheets only: AJIO MASTER.xlsx, MYNTRA SPF MASTER.xlsx, MYNTRA SJIT SPF
                     MASTER.xlsx (SJIT / FBM returns and claims, own file: owner, 25 Nov 2026) (owner, 24 Nov 2026:
                     kept only here; core/drive.py spf_master). Their hand inputs stay in Drive SPF/AJIO/input and
                     SPF/MYNTRA/input (MYNTRA_SPF_FOLDER_ID, SPF_MANUAL_DRIVE_FILE_ID, SPF_OMS_DRIVE_FILE_ID)
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

## Agent context and token use

The owner's TOKEN OPTIMIZATION RULES are in AGENTS.md. Keep PROJECT_CONTEXT.md concise and current;
read task-relevant files, prefer targeted edits, exclude unrelated generated files, and preserve correctness.

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

R2 app-update storage must stay within the free allowance (owner, 24 Nov 2026). The dedicated
ultron-app-releases bucket is Standard and private. Its app API stops at 2 GB total upload reservations,
10,000 Class A calls and 100,000 Class B calls per UTC month. Stop updates rather than pay overage;
never reset accounting blindly or enable public bucket URLs. Unrelated account use is outside these guards.
See docs/apps/app-updates.md; Cloudflare has no R2 billing cap.

The app and Telegram use one permission-checked agent control service (owner, 24-25 Nov 2026).
Preview must never dispatch or mutate state. App chat uses its claimed job's current account permissions;
changes wait for approval except allowed automatic reports. Runtime schedule revisions are shared with
reporting, not copied into separate client configurations. See docs/apps/shared-controls.md.

## Settings and secrets — never in git

- **Public repo**: every workflow runs its bot through `scripts/github/ci_run.sh` (public log = exit code
  only; log + `output/` uploaded AES-encrypted with `ARTIFACT_KEY`; read with
  `python scripts/github/run_output.py <run id>`). Never commit or print logins, cookies or customer data;
  folder / file ids and chat ids live in secrets.
- Local: one `.env` (copy of `.env.example`) + `service_account.json` (Google service account
  `ajio-tat-bot@storied-port-441507-k7.iam.gserviceaccount.com`, Editor on the folders). Ignored by
  git, as are the output folder (outside the source code, `ultron/core/paths.py`), workbooks, CSVs, captures, `myntra_session*.json`, `scripts/*.txt`.
- GitHub: repository **Secrets** (logins, Drive ids, `GOOGLE_SERVICE_ACCOUNT_JSON`,
  `GOOGLE_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN`, `ARTIFACT_KEY`) and **Variables** (tuning). `SPF_DRY_RUN=0` = AJIO SPF
  posts for real. A blank GitHub variable arrives as an empty string and falls back to the default.
  Variables with no default, also in the local `.env` (the code holds no Drive id, `tests/test_no_ids_in_repo.py`
  checks it; a run without one stops and names it): `AGENT_WORK_FOLDER_ID`, `MYNTRA_OTP_SHEET_ID`, `POD_MASTER_SHEET_ID`, `SMS_SHEET_ID`.
  Their old values remain in the git history.
- WhatsApp alerts: secrets `CALLMEBOT_PHONE`, `CALLMEBOT_APIKEY` (`integrations/whatsapp.py`, CallMeBot, free for personal use: the owner's own number, text only, no replies). They pass through an outside service, so no customer data or log lines. Telegram stays the main channel. Today: the morning report and the watcher's alerts.
- Cloudflare worker secrets: see `docs/bots/worker-and-dashboard.md`.
- New Drive files need the owner's OAuth token (the service account cannot create files): `docs/PORTALS.md`.

## Hand-run tools the workings came from (still in their Drive folders)

`RETURN ANALYSIS/main.py` → returns renderer (since 19 Nov 2026 the active bot's customer-return
counts come from Business Reporting's shared builders, using the same archived sources) ·
`SPF/MYNTRA/main.py` → myntra-spf · `SPF/AJIO/main.py` →
ajio-spf (`master_engine.py`) · `AGENT WORK/AJIO/Ajio Ads Gap Working/main.py` → ajio-ads.
