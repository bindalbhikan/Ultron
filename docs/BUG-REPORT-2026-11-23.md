# Bug report: 23 Nov 2026

A check of the whole agent after the portal sale report left Myntra, AJIO and Flipkart out (run 45170263771).

**How it was checked**
- the latest run log of every bot, then every bot run since pandas was removed (22 Nov, 20:55): 44 runs;
- pyright over all of `src/`, plus a search for pandas methods left on Polars tables;
- a test that every import in the code exists (new);
- the full test suite (217 pass), ruff, and the app API's type check and tests (13 pass);
- test runs with nothing posted or uploaded: evening summary, ERP to OMSGuru returns, business report (Oct-26),
  return analysis (Oct-26);
- the agent's chat with read-only questions.

## Fixed today (all pushed to main)

| # | Bug | Effect | Fix | Commit |
|---|---|---|---|---|
| 1 | Portal sale still imported `to_polars`, which went with pandas | Myntra, AJIO and Flipkart left out of the 5:30 PM report (cells kept old values, nothing wrong written) | calls removed; re-run 45177602636 read every portal and left nothing out | 17ed725 |
| 2 | No check caught an import of a removed name inside a function | the same kind of bug could come back | `tests/test_imports_resolve.py` checks every `from ultron... import` | 17ed725 |
| 3 | Google retired `gemini-2.5-pro` (404 "no longer available") but the agent still picked it | every smart call to Google failed and fell back to a slower model (morning report, weekly review) | `gemini-pro-latest` first; the app's model list too | d91ba10, c495aae |
| 4 | AJIO TAT `probe` called pandas' `to_string` on a Polars table | the login check would crash | prints the Polars table | d91ba10 |
| 5 | Morning / evening table: a change of +100% or more ran into the number before it (`24+317%`) | hard to read on the phone | shown as a multiple (`4.2x`); the table stays 28 wide | d91ba10 |
| 6 | The agent gave GitHub's UTC times as the owner's time and counted 1 zero TD failure of 3 | wrong answer to "which bots failed today" | runs now carry `started_local`; checked again: 3 failures, IST times | 1ab32d0, 96da774 |
| 7 | The agent's knowledge pages did not name 4 Myntra portal calls the code uses (`getComments`, `updateClaim`, `getWaitingTime`, `last-payment`) | the agent guessed a wrong API for SPF ticket comments | added to `docs/knowledge/myntra-partner.md`; every portal call in the code is now named | 8f0515e, 961d4e2 |
| 8 | On a PC with only the Microsoft Store Python, `.venv` was built on it | bot outputs and run logs were saved into a hidden Store folder, not `%LOCALAPPDATA%\Ultron\output` | `setup_pc.ps1` uses uv's own Python 3.12 (as GitHub) and rebuilds such a venv | c0eeba1 |

Also cleaned up: the 4 test questions were removed from the owner's agent chat memory (the 6 real turns kept as they
were), and the run watcher's portal sale incident note now says it is fixed.

## Checked and fine

- Evening summary, ERP to OMSGuru returns (test mode: nothing accepted), business report Oct-26 (matches the agent:
  Myntra return 31.9%, RTO 12.5%), return analysis Oct-26: all OK.
- App API: type check clean, 13 tests pass. Worker and dashboard scripts: no syntax errors.
- Myntra courier scorecard (evening run): OK.

## Open: for tomorrow

**Owner (data / decisions)**
1. **Return analysis COST is blank**: `Cost Sheet.xlsx` is not in Drive `RETURN ANALYSIS/Supporting`, so the 15 Nov
   run had no COST for 8,085 MYNTRA MAIN rows, 4,074 DBCC, 197 FMCC and 3,148 AJIO. Upload the sheet, or decide another
   source (the zero TD sheet has a COST column per style).
2. **EXIM tab missing** in `MYNTRA ZERO TD UPDATE SHEET.xlsx`: zero TD checks MAIN, DBCC, FMCC and names EXIM as left
   out. Add the tab if EXIM styles should be checked.
3. **Phone Agent mode** was off 7-10 AM: zero TD failed 3 times (fine from 11 AM). Keep the ULTRON app in Agent mode
   before 7 AM.
4. **Google AI Studio key**: the pro models answer "quota exceeded" on this free key, so smart calls go to NVIDIA.
   A paid key, or Google moved down the model order, if Google should answer.
5. Business report Oct-26: "EXIM ORDER / RETURN: none" (new account, no saved reports for old months). Expected?
6. Return analysis: Flipkart and AJIO reports have no customer state, so Zone Wise / State Wise sheets are skipped for
   them. Expected?

**Code / checks**
7. **Myntra daily reports**: FMCC report jobs stay CREATED / IN_PROGRESS on Myntra's side past the wait (failed 21 Nov,
   and 9:30 AM + 12:30 PM on 23 Nov). Decide: a longer wait, or a later retry round for FMCC only.
8. Myntra SPF master: Myntra answers "Internal server error while scheduling report job" for report 4, and
   `getComments` errors on some MAIN tickets (portal side; retried). Watch the next runs.
9. Tonight's 8 PM bots are the first runs on the all-Polars code: ticket follow-up, Myntra colour grouping, ERP to
   OMSGuru returns, evening summary. The last two passed test runs here. The first two were not run locally (a local
   run could renew the Myntra portal login and break GitHub's copy): check their results tomorrow.
10. The app build for c495aae (format fix) was still running at the end of the day: check it passed.
11. `portal_sale/numbers.py` `read_report` still reads workbooks with openpyxl (to keep AJIO's spaces as before); the
    library rule says calamine. Move it with a same-output check.
12. On this PC, `D:\ULTRON\.git`'s `origin/main` pointer was found empty once (fixed by a fetch; `git fsck` clean).
    Watch for it again.
