# MasterSheet — `python run.py master-sheet`

**When**: 1:00 AM daily (owner, 24 Nov 2026). On demand: the `master-sheet.yml` workflow by hand (`no_upload=1` = a test
run, the sheet only in the run's artifact).

**Result**: `AGENT WORK/MASTER SHEET/MasterSheet.xlsx` (by name, `workings/core/master_sheet.py`), the one SKU master
every working reads (business report, return analysis, Myntra colour grouping); the old copies in BUSINESS
REPORTING and RETURN ANALYSIS/Supporting are no longer read.

* **MasterData** = exactly the channel listings OMSGuru has (Channel Listings > Download Mapped Channel Listings, the
  warehouse chosen first), one row per channel + listing SKU + listing id. OMSGuru channel id -> the sheet's channel
  name in `master_sheet/build.py` `CHANNELS` (a new OMSGuru channel gets its OMSGuru name and is named on Telegram).
* A listing already on the sheet keeps every value it has; only `Product SkuCode (Reference Only)` follows OMSGuru, and a
  blank is filled. A new listing: SIZE SKU = OMSGuru's SKU, MY SKU = SIZE SKU without the size, MASTER SKU / MASTER
  STYLE CODE from the owner's **Master Sku** sheet (else SIZE SKU / MY SKU), Brand by the listing SKU's prefix (FSH-
  Fashfun ...), DESIGN-NO / COLOR / LAUNCH DATE / PORTAL LISTING DATE from the other rows of the same style when they
  all agree (DESIGN-NO else **Fabric Code**, LAUNCH DATE first from **Launch Date & Size Count**).
* **Portal ids**, the portal's own file first, then the sheet, then OMSGuru: Myntra style id / SKU code from each
  account's Myntra listing report (the 9:30 AM `myntra-reports` job reused); Flipkart FSN from the newest Flipkart
  listing file (`flipkart-listing-file`), else OMSGuru `Extra Param` (OMSGuru's FSN was wrong on 358 of 377 rows where
  they differed, 24 Nov 2026); Amazon ASIN from OMSGuru (Amazon `Extra Data`, Amazon DF the listing id, Amazon Smart
  the ASIN of the same listing SKU on Amazon); Meesho product id OMSGuru `Extra Key`; AJIO JIOCODE = the listing id's
  first 9 digits + `_` + the colour (lower case, no spaces). Meesho catalog id / product identifier have no source:
  kept as they are.
* **REMOVED LISTINGS**: a listing OMSGuru no longer has moves there with `REMOVED ON` (owner, 24 Nov 2026: kept so old
  orders still map; the readers read MasterData first, then this sheet). One that comes back moves back.
* The owner's sheets (Master Sku, Fabric Code, Launch Date & Size Count, any other) are written back cell for cell.
  The workbook is written anew with xlsxwriter; Drive keeps the old versions.
* **No sheet on a guess**: OMSGuru's export failing, or fewer listings than `MASTER_SHEET_MIN_SHARE` (0.7) of the
  sheet's rows, fails the run with nothing written. A Myntra listing report or the Flipkart file not read: those ids
  stay as they were and Telegram names it.
* First run, 24 Nov 2026 (test, not saved): 138,790 listings (14,220 new, 13,521 of them Meesho in OMSGuru's new SKU
  format), 41,310 to REMOVED LISTINGS (Amazon 11,723, Amazon Smart 11,484, Meesho 12,302, Flipkart 5,684), 1.4 min.
