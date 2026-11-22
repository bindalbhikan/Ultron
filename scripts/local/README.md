# Run a bot on this PC

Normally every bot runs on GitHub. To run one here (testing, or GitHub is down):

## Once

```
powershell -ExecutionPolicy Bypass -File scripts\local\setup_pc.ps1
```

(Git, the memory link and the venv: see "No PC is fixed" below. Run bots with
`%USERPROFILE%\.ultron\venv\Scripts\python.exe`.)

`.env` (copy of `.env.example` with the logins) and `service_account.json` must be in the project
folder.

## Run

```
python run.py <bot> [options]
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

### Git metadata outside Google Drive

On this PC, Git metadata is stored at
`%USERPROFILE%\.ultron\git\AGENT-ULTRON-BINDAL.git`; the repository's `.git` file points there.
Google Drive previously inserted `desktop.ini` into Git refs, breaking pulls and fetches.
Keeping metadata outside Drive prevents recurrence for all Git clients, without a cleanup hook
or scheduled task. Normal `git pull`, `git fetch`, and `git push` commands work unchanged.

The migration on 14 November 2026 verified the copied files and preserved the original metadata
in ignored `output/git-metadata-backup-20261114`. The existing linked worktree was repaired to use
the new metadata location. Local uncommitted changes were preserved.

The `.git` pointer syncs through Drive to every PC, so it cannot name a per-user path: on 22 Nov 2026
it named `C:/Users/<other user>/...` and Git failed on the second PC ("not a git repository"). It now
points to `C:/ProgramData/Ultron/git/AGENT-ULTRON-BINDAL.git`, which on each PC is a junction to that
user's own `%USERPROFILE%\.ultron\git\AGENT-ULTRON-BINDAL.git`. Do not edit `.git` to a
`C:/Users/...` path again.

### No PC is fixed: `setup_pc.ps1`

Owner's rule (22 Nov 2026): any PC may be the one in use and any may be switched off for good, so nothing
that matters lives only on a PC. On Drive: the project files, `.env`, `service_account.json`, and Claude
Code's memory for this project (`..\AGENT-MEMORY\AGENT-ULTRON-BINDAL`). On GitHub: the code history, so
**push before leaving a PC**. On a new PC (or when Git says "not a git repository") run once, no admin:

```
powershell -ExecutionPolicy Bypass -File scripts\local\setup_pc.ps1
```

It rebuilds the Git metadata from GitHub if this PC has none (working files untouched; local edits show as
changes), makes the `C:\ProgramData\Ultron` junction, links Claude Code's memory folder to Drive (notes
already on the PC are copied there first), and builds the venv in `%USERPROFILE%\.ultron\venv` with uv.
Safe to run again. Do not recreate a `.git` directory inside Drive or run cleanup commands that assume
`.git` is a folder.

### Bot runs

* Do not run a Myntra bot here while the same bot runs on GitHub: Myntra refuses the same report
  twice within 15 minutes, so both runs lose reports.
* The local `FLIPKART_PASSWORD` was out of date on 18 Oct 2026 (the GitHub secret works): update
  `.env` before running Flipkart parts locally, and do not retry a failing Flipkart login.
