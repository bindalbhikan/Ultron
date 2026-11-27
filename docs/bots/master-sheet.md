# MasterSheet — `python run.py master-sheet`

**When**: 1:00 AM daily (owner, 24 Nov 2026; the worker's cron `30 19 * * *` UTC, `SCHEDULE` in `worker/src/worker.js`,
since 25 Nov 2026). On demand: `/mastersheet`, the 📋 MasterSheet button (All channels menu), or the `master-sheet.yml`
workflow by hand (`no_upload=1` = a test run, the sheet only in the run's artifact).

**Result**: `AGENT WORK/MASTER SHEET/MasterSheet.xlsx` (by name, `workings/core/master_sheet.py`), the one SKU master
every working reads (business report, return analysis, Myntra colour grouping, Myntra zero TD's brand / SKU) and the
chat agent answers from (`sku_lookup`, `master_sheet_query` in `workings/agent_tools.py`; owner, 25 Nov 2026: the one
central SKU master); the old copies in BUSINESS REPORTING and RETURN ANALYSIS/Supporting are no longer read. Sheet tabs in capitals (owner, 24 Nov 2026): MASTER DATA
(was MasterData), PORTAL COMBINED, then the owner's MASTER SKU, FABRIC CODE, LAUNCH DATE & SIZE COUNT; the readers find a sheet whatever its case (`master_sheet.sheet_of`).

* **The owner's OMSGuru mapping tool, same to same** (owner, 26 Nov 2026: "humari mastersheet wrong update ho rahi he
  ... ye old tool he same to same use kar lo"): `master_sheet/legacy.py` is
  `G:/My Drive/BINDAL EXPORTS/OMSGURU MAPPING/update_master.py` line for line (from its first constant on, not one
  line added; only its writer, `master.db` and command line left out). Its Excel reading goes through
  `master_sheet/xlcompat.py` (python-calamine giving the values openpyxl / xlrd gave), so no openpyxl / xlrd. Checked
  on 26 Nov 2026 inputs: the same 167,079 MASTER DATA rows and 92,692 PORTAL COMBINED rows as the old tool, cell
  for cell, and every count it prints (81 s against its 4 min).
* Its **input/** folder = every file in `AGENT WORK/MASTER SHEET/PORTAL SHEET` (the owner's portal exports, told
  apart by their header row: Myntra listing / style, AJIO-INV-<brand>, Flipkart, Amazon, Meesho, Nykaa, Snapdeal ...)
  + OMSGuru's channel listing mapping export, pulled fresh each run. Its **supporting/** files = the owner's sheets
  in the workbook: MASTER SKU (= Final Sku Sheet; MASTER SKU / MASTER STYLE CODE read as FINAL SIZE SKU / FINAL MY
  SKU), FABRIC CODE (a code merged over a SKU group counts for every row), LAUNCH DATE & SIZE COUNT (SKU + DATE).
* What the tool does, unchanged: new OMSGuru listings appended with MY SKU / SIZE SKU from the seller SKU (colour
  never in a SKU, it goes to COLOR), listings only on a portal file added, `Product SkuCode (Reference Only)` a copy
  of OMSGuru's, MY SKU / SIZE SKU re-synced, blank portal ids / COLOR / dates filled, MASTER SKU / MASTER STYLE CODE
  from MASTER SKU, DESIGN-NO from FABRIC CODE, a blank LAUNCH DATE from LAUNCH DATE; no row is ever deleted.
* **The one rule on top** (owner): a listing in OMSGuru's export stays in MASTER DATA, also one the tool used to park
  in `output/new_unmapped_listings.xlsx` for having no sized SKU (944 on 26 Nov 2026); a listing OMSGuru does not
  carry (found as the tool finds it: Channel Name + Channel Listing Id, else + Channel Listing SKU Code) is kept and
  marked `UNMAPPED` in **REMARK** (27,978 on 26 Nov 2026). Nothing else: no brand guessing, INFERRED BRAND, NEED DATA,
  UNMAPPED / REMOVED LISTINGS sheets any more.
* Sheets: MASTER DATA (the tool's 21 columns, FINAL SKU / FINAL MY SKU under the owner's names MASTER SKU / MASTER
  STYLE CODE, + REMARK), PORTAL COMBINED (the tool's every-portal sheet), then the owner's sheets cell for cell with
  their merged cells (`core/xlsx.write_sheets(merges=...)`; until 26 Nov 2026 the rewrite flattened FABRIC CODE's 71
  merges and 194 SKUs lost their fabric code: restored from the owner's 24 Nov version). Header row Accent2, frozen,
  filtered; days as mm-dd-yy as the tool wrote them. The workbook is written anew and replaces the same Drive file
  (Drive keeps the old versions); the run downloads it with edit access and refuses to overwrite a file changed on
  Drive while it ran (`DriveFile.download(need_edit=True)` / `upload`).
* Readers use MASTER DATA (`core/master_sheet.read`; older files' UNMAPPED / REMOVED LISTINGS still read).
* Test runs: `--no-upload` (Drive file, nothing saved), `--file <xlsx>`, `--base <xlsx>` (MASTER DATA from another
  workbook, e.g. the old tool's MasterSheet.xlsx), `--inputs <folder>` (a local input/ instead of PORTAL SHEET + OMSGuru).
* **No sheet on a guess**: OMSGuru's export failing, empty, or giving fewer listings than `MASTER_SHEET_MIN_SHARE`
  (0.7) of the sheet's rows fails the run with nothing written. A PORTAL SHEET file not read is named in Telegram.
* 27 Nov 2026: put back on the old tool's MasterSheet (its 26 Nov 12:17 run, 167,079 rows) as the base; the bot's
  own 24-26 Nov rebuilds (184,973 rows with REMOVED LISTINGS folded in, guessed brands) were the wrong updates.
