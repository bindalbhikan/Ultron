# Run a bot on this PC

Normally every bot runs on GitHub. To run one here (testing, or GitHub is down):

## Once

```
powershell -ExecutionPolicy Bypass -File scripts\local\setup_pc.ps1
```

(Private files, the memory link and the uv venv: see "No PC is fixed" below.)

`.env` (copy of `.env.example` with the logins) and `service_account.json` must be in the project
folder; the script restores them from Drive when they are missing.

## Run

```
.venv\Scripts\python run.py <bot> [options]
```

Bots: `sale`, `vms`, `ajio-tat`, `ajio-spf`, `returns`, `myntra-spf`, `ajio-ads`.
`python run.py <bot> --help` lists the options. Useful ones for a safe test:

| Bot | Test without changing Drive / Telegram |
|---|---|
| returns, myntra-spf, ajio-ads | `--no-upload --no-telegram` |
| sale, vms, ajio-tat | `--no-drive --no-telegram` |
| ajio-spf | `--dry-run --no-upload --no-telegram` (posts nothing on AJIO) |

Results and the log go to `output/<bot>/` (git-ignored, has customer data: delete when done).

`run_local.bat <bot> [options]` does the same and appends the output to `output\local_run.log`
(for Windows Task Scheduler).

## Rules

### The project lives at `D:\ULTRON`, off Google Drive

Since 22 Nov 2026 the checkout is a normal Git clone at `D:\ULTRON`. It was on Google Drive before,
where Drive's `desktop.ini` files broke Git refs and a Drive-synced `.git` pointer named one PC's user
folder, so Git failed on the other PC. The old Drive folder (`AGENT\AGENT-ULTRON-BINDAL`) is no longer
worked in.

### No PC is fixed: `setup_pc.ps1`

Owner's rule (22 Nov 2026): any PC may be the one in use and any may be switched off for good, so nothing
that matters lives only on a PC:

* code history: GitHub, so **push before leaving a PC** (no work left only in local commits or stashes);
* private files (`.env`, `service_account.json`, `myntra_session*.json`): a copy on Drive in
  `AGENT\AGENT-PRIVATE\ULTRON`; run the script with `-Backup` after changing one;
* Claude Code's memory for this project: on Drive in `AGENT\AGENT-MEMORY\AGENT-ULTRON-BINDAL`, linked;
* the venv: `.venv` in the project, rebuilt by uv from `uv.lock`.

On a new PC, no admin:

```
git clone https://github.com/bindalbhikan/Ultron.git D:\ULTRON
powershell -ExecutionPolicy Bypass -File D:\ULTRON\scripts\local\setup_pc.ps1
```

It restores the private files from Drive, links the memory folder (notes already on the PC are copied to
Drive first), installs uv if missing and builds `.venv` (all extras, plus pytest, ruff, pyright). Safe to
run again. Do not set `UV_PROJECT_ENVIRONMENT`: the venv is the project's `.venv`.

### Bot runs

* Do not run a Myntra bot here while the same bot runs on GitHub: Myntra refuses the same report
  twice within 15 minutes, so both runs lose reports.
* The local `FLIPKART_PASSWORD` was out of date on 18 Oct 2026 (the GitHub secret works): update
  `.env` before running Flipkart parts locally, and do not retry a failing Flipkart login.
