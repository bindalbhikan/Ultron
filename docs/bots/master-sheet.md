# MasterSheet — `python run.py master-sheet`

**When**: 1:00 AM daily (owner, 24 Nov 2026; the worker's cron `30 19 * * *` UTC, `SCHEDULE` in `worker/src/worker.js`,
since 25 Nov 2026). On demand: `/mastersheet`, the 📋 MasterSheet button (All channels menu), or the `master-sheet.yml`
workflow by hand (`no_upload=1` = a test run, the sheet only in the run's artifact).

**Result**: `AGENT WORK/MASTER SHEET/MasterSheet.xlsx` (by name, `workings/core/master_sheet.py`), the one SKU master
every working reads (business report, return analysis, Myntra colour grouping, Myntra zero TD's brand / SKU) and the
chat agent answers from (`sku_lookup`, `master_sheet_query` in `workings/agent_tools.py`; owner, 25 Nov 2026: the one
central SKU master); the old copies in BUSINESS REPORTING and RETURN ANALYSIS/Supporting are no longer read. Sheet tabs in capitals (owner, 24 Nov 2026): MASTER DATA
(was MasterData), NEED DATA, UNMAPPED LISTINGS, REMOVED LISTINGS, then the owner's MASTER SKU, FABRIC CODE, LAUNCH
DATE & SIZE COUNT; the readers find a sheet whatever its case (`master_sheet.sheet_of`).

* **MASTER DATA** retains listings from the existing master and both historical listing tabs. It includes all
  identifiable listings from the portal files and all channels in the OMSGuru mapped export, including paused
  channels. `REMARK` contains `UNMAPPED` when the listing is absent from the export. A later match clears this
  marker and preserves other remarks.
* A listing already on the sheet keeps every value it has; only `Product SkuCode (Reference Only)` follows OMSGuru, and a
  blank is filled. A new listing: SIZE SKU = OMSGuru's SKU, MY SKU = SIZE SKU without the size, MASTER SKU / MASTER
  STYLE CODE from **MASTER SKU** (else SIZE SKU / MY SKU), DESIGN-NO / COLOR / LAUNCH DATE / PORTAL LISTING DATE from
  the other rows of the same style when they all agree (DESIGN-NO else **FABRIC CODE**, LAUNCH DATE first from
  **LAUNCH DATE & SIZE COUNT**).
* **Brand** (26 Nov 2026): portal brands take precedence. AJIO B2C InventoryView uses the second header row,
  Seller SKU and the brand in the AJIO-INV filename. Blank brands can use unanimous same-channel listing style or
  master style, a listing style shared by two branded channels, or a same-channel prefix supported by five styles.
  Portal placeholders such as the literal text null count as missing. Conflicting candidates stay blank. INFERRED BRAND records each guess and the next run recalculates it.
* **Portal ids**, the portal's own file first, then the sheet, then OMSGuru: Myntra style id / SKU code from each
  account's Myntra listing report (the 9:30 AM `myntra-reports` job reused); Flipkart FSN from the newest Flipkart
  listing file (`flipkart-listing-file`), else OMSGuru `Extra Param` (OMSGuru's FSN was wrong on 358 of 377 rows where
  they differed, 24 Nov 2026); Amazon ASIN from OMSGuru (Amazon `Extra Data`, Amazon Smart the ASIN of the same
  listing SKU on Amazon); Meesho product id OMSGuru `Extra Key`; AJIO JIOCODE = the listing id's first 9 digits + `_` +
  the colour (lower case, no spaces). Meesho catalog id / product identifier: only from PORTAL SHEET.
* **PORTAL SHEET** accepts CSV, tab-separated TXT, XLS and XLSX exports. MASTER DATA includes the source
  columns under portal-prefixed headings. Matching uses listing ID then seller SKU within the portal or
  Myntra account. Meesho uses product ID plus variation, and style ID plus variation for the seller SKU.
  Myntra style files enrich listings by account and style ID. Files with unidentified listing keys are named
  in the run summary. The older mapping tool supplied the portal identifier conventions.
* **NEED DATA** (owner, 24 Nov 2026: only the portal and the file it needs): one row per channel with listings missing
  a value a portal file gives (Brand, COLOR, the channel's portal ids: Myntra style id + SKU code, Flipkart FSN, Amazon
  ASIN, Meesho product + catalog id, AJIO JIOCODE): PORTAL, CHANNEL, FILE NEEDED (e.g. "AJIO inventory file",
  "Meesho inventory / catalog file"), LISTINGS MISSING DATA, MISSING (each value with its count). 24 Nov: 9 channels.
* **UNMAPPED LISTINGS** shows the marked rows from MASTER DATA. **REMOVED LISTINGS** keeps the historical
  archive. Readers use MASTER DATA directly in this layout, and still read all three tabs in older files.
* Header row of every sheet: Excel's Accent2 style (fill #C0504D, bold white; owner, 24 Nov 2026), frozen, filtered.
  The owner's sheets are written back cell for cell; the workbook is written anew with xlsxwriter and replaces the
  same Drive file (Drive keeps the old versions). The run downloads it with edit access and refuses to overwrite a
  file changed on Drive while it ran (`DriveFile.download(need_edit=True)` / `upload`).
* **No sheet on a guess**: OMSGuru's export or channel list failing, or fewer listings than `MASTER_SHEET_MIN_SHARE`
  (0.7) of the sheet's rows, fails the run with nothing written. A Myntra listing report, the Flipkart file or a
  PORTAL SHEET file not read: those values stay as they were and Telegram names it.
* 26 Nov 2026: 184,973 listings in MASTER DATA (118,830 previously on the sheet, 61,419 kept from REMOVED LISTINGS,
  4,724 new), 46,076 marked UNMAPPED, 7,101 without a brand, 11 channels in NEED DATA; MASTER DATA has the 22
  standard columns + INFERRED BRAND + REMARK only (portal raw columns not written); about 2.5 min.
