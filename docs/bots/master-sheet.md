# MasterSheet — `python run.py master-sheet`

**When**: 1:00 AM daily (owner, 24 Nov 2026). On demand: the `master-sheet.yml` workflow by hand (`no_upload=1` = a test
run, the sheet only in the run's artifact).

**Result**: `AGENT WORK/MASTER SHEET/MasterSheet.xlsx` (by name, `workings/core/master_sheet.py`), the one SKU master
every working reads (business report, return analysis, Myntra colour grouping); the old copies in BUSINESS
REPORTING and RETURN ANALYSIS/Supporting are no longer read. Sheet tabs in capitals (owner, 24 Nov 2026): MASTER DATA
(was MasterData), NEED DATA, UNMAPPED LISTINGS, REMOVED LISTINGS, then the owner's MASTER SKU, FABRIC CODE, LAUNCH
DATE & SIZE COUNT; the readers find a sheet whatever its case (`master_sheet.sheet_of`).

* **MASTER DATA** = the listings of OMSGuru's **Active** channels (Channel Listings > Download Mapped Channel Listings,
  the warehouse chosen first; owner, 24 Nov 2026: a Paused / Disabled channel's listings go to REMOVED LISTINGS, named
  on Telegram: AJIO and LimeRoad paused, Amazon DF disabled on 24 Nov). Status from Channel > List Channels, its
  all-channels tab `/channel_companies/index/4` (`OmsGuruClient.channels(every=True)`; without it only the Active
  ones, as inv-push and listings use them). One row per channel + listing SKU + listing id; OMSGuru channel id -> the
  sheet's channel name in `master_sheet/build.py` `CHANNELS`.
* A listing already on the sheet keeps every value it has; only `Product SkuCode (Reference Only)` follows OMSGuru, and a
  blank is filled. A new listing: SIZE SKU = OMSGuru's SKU, MY SKU = SIZE SKU without the size, MASTER SKU / MASTER
  STYLE CODE from **MASTER SKU** (else SIZE SKU / MY SKU), DESIGN-NO / COLOR / LAUNCH DATE / PORTAL LISTING DATE from
  the other rows of the same style when they all agree (DESIGN-NO else **FABRIC CODE**, LAUNCH DATE first from
  **LAUNCH DATE & SIZE COUNT**).
* **Brand only from a portal's own sheet** (owner, 24 Nov 2026): a Myntra listing's from its account's Myntra listing
  report, a Flipkart one's from the Flipkart listing file (spelt as the sheet spells it, FashFun -> Fashfun), any
  channel's from the owner's PORTAL SHEET files. Otherwise the sheet's own Brand stays, unless it is wrong (a SKU
  brand code like "FSH", or "Shopsy", a Flipkart marketplace): that one, and a new listing's, stays blank and is listed
  in NEED DATA. Nothing from titles, other channels or SKU prefixes (that put "Fashfun" on BINDAL EXIM, which has no
  such brand). On 24 Nov the brands the earlier runs had filled that way were set back to the owner's own.
* **Portal ids**, the portal's own file first, then the sheet, then OMSGuru: Myntra style id / SKU code from each
  account's Myntra listing report (the 9:30 AM `myntra-reports` job reused); Flipkart FSN from the newest Flipkart
  listing file (`flipkart-listing-file`), else OMSGuru `Extra Param` (OMSGuru's FSN was wrong on 358 of 377 rows where
  they differed, 24 Nov 2026); Amazon ASIN from OMSGuru (Amazon `Extra Data`, Amazon Smart the ASIN of the same
  listing SKU on Amazon); Meesho product id OMSGuru `Extra Key`; AJIO JIOCODE = the listing id's first 9 digits + `_` +
  the colour (lower case, no spaces). Meesho catalog id / product identifier: only from PORTAL SHEET.
* **PORTAL SHEET** folder (`AGENT WORK/MASTER SHEET/PORTAL SHEET`, owner, 24 Nov 2026): the owner's files (xlsx, every
  sheet, or csv) with MASTER DATA's column names (any case / spacing; `Channel Listing SKU Code` needed, `Channel
  Name` optional). Read every run, newest file last; a filled cell there wins over everything (Brand included); an
  empty cell changes nothing. The NEED DATA sheet, filled in, works as it is.
* **NEED DATA**: the MASTER DATA rows with a value missing, `MISSING` first naming them: Brand, DESIGN-NO, COLOR, and the
  channel's portal ids (Myntra style id + SKU code, Flipkart FSN, Amazon ASIN, Meesho product + catalog id, AJIO
  JIOCODE). Written anew each run, not read by the workings.
* **UNMAPPED LISTINGS** (owner, 24 Nov 2026): a listing in a portal's own listing file (each Myntra account's listing
  report, the Flipkart listing file) that OMSGuru does not have, in MASTER DATA's columns: SKU columns from the same
  listing SKU elsewhere on the sheet, else the listing SKU without its brand code (FSH-DRESS-A-1-L -> DRESS-A-1-L;
  DRESS- stays), then worked out as a new listing. Written anew each run; the readers read it after MASTER DATA
  (24 Nov: 121, 119 of them Myntra EXIM, brand CORSICA).
* **REMOVED LISTINGS**: a listing OMSGuru no longer has, or of a channel no longer Active, moves there with `REMOVED ON`
  (owner, 24 Nov 2026: kept so old orders still map; the readers read it last). One that comes back moves back.
* Header row of every sheet: Excel's Accent2 style (fill #C0504D, bold white; owner, 24 Nov 2026), frozen, filtered.
  The owner's sheets are written back cell for cell; the workbook is written anew with xlsxwriter (Drive keeps the
  old versions).
* **No sheet on a guess**: OMSGuru's export or channel list failing, or fewer listings than `MASTER_SHEET_MIN_SHARE`
  (0.7) of the sheet's rows, fails the run with nothing written. A Myntra listing report, the Flipkart file or a
  PORTAL SHEET file not read: those values stay as they were and Telegram names it.
* 24 Nov 2026: 118,721 listings of 13 Active channels, 61,379 on REMOVED LISTINGS (20,069 of them the paused / disabled
  channels), 121 unmapped, 14,789 without a brand, 32,795 in NEED DATA; about 1.5 min.
