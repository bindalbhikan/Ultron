# R2: free allowance only (owner, 24 Nov 2026)
User enabled R2 and requires staying inside the free tier. Account had no buckets; created dedicated ultron-app-releases in Standard, disabled r2.dev.
Cloudflare has no R2 hard spend limit. Deployed pre-operation D1 counters: 10,000 Class A/month, 100,000 Class B/month; storage reservations capped at 2,000,000,000 bytes across all uploads and releases.
Reservations never automatically reset/refund, including failed uploads; pause uploads at storage cap. Parts must exactly match reserved size. Free allowance is account-wide, so unrelated direct/bucket usage is outside app guards.
Live multipart completion did not return the required persisted metadata; verify via a guarded HEAD before publishing. Its failed attempt keeps its reservation.
Published all four packages (0.1.24/build 124) via rerun of publish job 45383631102. All checksums and sizes verified live. Reservations: 172,509,039 bytes including a failed first Android attempt; actual release bytes: 109,851,386. D1 counters at publication: 31 Class A; download verification adds a handful of Class B. All far below limits.
Live HEAD/full GET exposed R2 full-object range metadata; return 200 unless GET explicitly includes Range. Android updater requires full-download 200. Added regression assertions for HEAD/full/ranged statuses.
Do not bypass these guards with direct uploads, public URLs, custom domains or Infrequent Access.
