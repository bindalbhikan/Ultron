# Project context

Updated: 26 Nov 2026.

- Active checkout: D:\ULTRON; the Google Drive checkout is retired. Read AGENTS.md first.
- Ultron: seller-neutral agent core, seller workings, Cloudflare operations worker, app API and Flutter app.
- Completed (26 Nov): MasterSheet keeps every historical and portal listing in MASTER DATA, marks a listing absent
  from OMSGuru as UNMAPPED in REMARK, and imports every PORTAL SHEET file (CSV, tab-separated TXT, XLS, XLSX) under
  portal-prefixed columns. Rebuilt from the current Drive workbook and uploaded to
  `AGENT WORK/MASTER SHEET/MasterSheet.xlsx`: 184,973 listings, 46,076 marked UNMAPPED.
- Verified: 269 Python tests (1 skipped), ruff clean, docs in step. The rebuilt workbook contains all 118,828
  previous MASTER DATA keys, all 61,419 REMOVED LISTINGS keys and both old UNMAPPED keys; the owner's MASTER SKU,
  FABRIC CODE and LAUNCH DATE & SIZE COUNT sheets are identical; every identifier in the portal files is present;
  no duplicate listing keys.
- Upload safety: the run downloads the MasterSheet with edit access and refuses to overwrite a file changed on
  Drive during the run (`DriveFile.download(need_edit=True)` / `upload`).
- Done (26 Nov): committed and pushed (c435754); MASTER DATA has exactly 23 columns. Adopted useful logic from old OMSGuru mapping tool: colour stripping, size normalization, AJIO JioCode mapping, Meesho constructed SKU, prefix->brand mapping. INFERRED BRAND captures statistical inference before fallbacks. Tests/Lint/Docs sync pass. Drive upload verified (184,978 rows, 23 columns).
- Readers use MASTER DATA directly in the new layout (historical rows are in it); older workbooks still read
  MASTER DATA, UNMAPPED LISTINGS and REMOVED LISTINGS.
- Durable implementation notes: .serena/memories/workings/core.md; product docs: docs/bots/master-sheet.md.
