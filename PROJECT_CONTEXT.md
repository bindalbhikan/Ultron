# Project context

Updated: 26 Nov 2026.

- Active checkout: D:\ULTRON; the Google Drive checkout is retired. Read AGENTS.md first.
- Ultron: seller-neutral agent core, seller workings, Cloudflare operations worker, app API and Flutter app.
- Active (27 Nov): MasterSheet = the owner's OMSGuru mapping tool same to same (master_sheet/legacy.py, reading via
  xlcompat.py/calamine). Owner rule: in OMSGuru's export -> stays in MASTER DATA (parked no-size rows too); not in it ->
  REMARK UNMAPPED; nothing else (build.py/portal.py, INFERRED BRAND, NEED DATA, UNMAPPED/REMOVED sheets removed).
- Verified: on 26 Nov inputs the port gives the old tool's 167,079 MASTER DATA + 92,692 PORTAL COMBINED rows cell for
  cell; +944 parked rows, 27,978 UNMAPPED. Owner's sheets keep merges (write_sheets merges=); FABRIC CODE's 71
  merges (194 fabric codes) restored from the owner's 24 Nov Drive version.
- Base: the Drive MASTER DATA is reset to the old tool's MasterSheet (26 Nov 12:17 run) with `--base` / `--sheets`.
- Durable implementation notes: .serena/memories/workings/core.md; product docs: docs/bots/master-sheet.md.
