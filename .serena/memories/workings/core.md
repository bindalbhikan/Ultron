# Workings invariants
- Pipeline entrypoint run.py dispatches to src/ultron/workings/<working>/pipeline.py. Shared clients/storage/reporting in workings/core; API clients in workings/portals.
- Business Reporting builders are canonical for returns. return_analysis/reconciled.py selects/renders their order lines and check_against_business compares units before publication. Read docs/bots/returns.md and business-report.md before changes.
- Analysis sold units = Delivered + Customer Return; returned units = Customer Return, same order month/account and archived sources. Rebuild from saved PORTAL REPORTS, never newly requested reports during reconciliation.
- Return windows run through next month's 14th; partial sources are named and omitted as needed. Preserve partial quantities, cancellations/RTO distinctions and line identifiers.
- Daily return-delivery workbook updates require validated Orders; stale/missing Orders leave account rows unchanged. Pending job snapshots refresh before enforcing a shared wait deadline.
- Portal report requests reuse completed usable jobs; Myntra duplicate report cooldown is 15 minutes. Do not run the same local Myntra bot concurrently with GitHub.
- Phone jobs wait for reconnect within the existing total job budget before queueing; an offline timeout queues no work and never fabricates results.
- Safe flags vary: sale/vms/ajio-tat use --no-drive --no-telegram; returns/myntra-spf/ajio-ads use --no-upload --no-telegram; ajio-spf also needs --dry-run. Confirm each parser; no blanket assumption that flags suppress every portal write.
- New working integration checklist includes workflow, watcher, command/menu, schedule, dashboard, run.py, docs page and sync.
