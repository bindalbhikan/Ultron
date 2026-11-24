# Implementation conventions
- English only in code/comments/docs/logs/commits/PRs and messages.
- Centralize: portal login workings/core/clients.py; retry ultron/core/retry.py; Drive folders agent_folder(); new xlsx workings/core/xlsx.py; portal answer validation workings/core/shapes.py; ids/columns workings/core/tables.py. See docs/CENTRALISE.md.
- Myntra account definitions only in workings/portals/myntra.py SELLERS/ACCOUNTS; do not hardcode copies in workings.
- A working exposes pipeline.run(args), pipeline.main(argv) and shared run_bot() wiring. run.py BOTS maps command names; one docs/bots page and watched workflow per working.
- Preserve values on library migrations using identical inputs and output parity. Library changes have an ordered docs/libraries page. Rewrite changing workbooks with approved readers/writers.
- Never log out of Myntra, solve CAPTCHA, or bypass reCAPTCHA. AJIO SPF tickets/replies only Wednesday/Saturday; never close Myntra SPF claims before receipt/payment.
- Source failures must not overwrite valid existing workbook data. Never turn missing values into fabricated zero totals.
- Changes include matching docs and memory. Generated AUTO blocks are owned by scripts/docs/sync_docs.py, never edited manually.
