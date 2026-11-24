# App updates through Cloudflare

Status (24 Nov 2026): R2 enabled; dedicated Standard bucket ultron-app-releases connected with application limits below the free allowance.
Release 0.1.24 (build 124) is published for Android, Windows, macOS and Linux; live downloads passed byte-count and SHA-256 verification.
Cloudflare has no R2 product spending limit. These guards cover this app's managed bucket traffic, not unrelated account usage or direct administrator/API access.

The app checks the public app API at startup and offers a newer build inside every screen, including SMS only.
Profile also provides Check for updates. Version and build come from CI through Dart defines.

Android streams the APK into private cache, checks byte count, SHA-256, package id and a strictly newer version code, then opens Android's installer.
The user allows ULTRON as an installation source once and confirms each installation. Android enforces the signing key; CI uses the existing Ultron Phone key.
Desktop updates open the Cloudflare download in the system browser; the user opens the package. No silent desktop replacement. iOS and web do not advertise native updates.
Old installations need the first updated package installed from Drive once to gain the updater.

## Storage and publication

The RELEASES binding in services/app_api/wrangler.jsonc connects the dedicated bucket ultron-app-releases.
The bucket uses Standard storage. Public r2.dev access is disabled and no custom domains are attached.
Incomplete multipart uploads under releases/ expire after one day. No Infrequent Access transition is configured.
The owner enabled R2; the agent did not change the account's billing plan.
Migration 0009_app_release.sql keeps the current completed build per platform. Its conditional update prevents an older CI run from replacing a newer release.

CI retains the Drive packages, then scripts/github/app_updates.py uploads successful packages in 10 MB multipart chunks through the app API.
APP_UPDATES_API is the public app API origin; DASHBOARD_TOKEN is the existing private CI credential, matching the app API WORKER_TOKEN.
Credentials and Drive links are not printed. The manifest advances after multipart completion and a guarded HEAD verifies the persisted size and reservation metadata.
Failed uploads fail publication explicitly and preserve the previous manifest. Missing platform builds never create a new manifest.
R2 keys contain build, platform and SHA-256.

## Free allowance guards

The owner's rule is to stay within the free allowance. Migration 0010_release_limits.sql stores accounting in D1.
Fixed application ceilings are deliberately much smaller than Cloudflare's account-wide Standard allowance:

| Resource | Application cutoff | Cloudflare Standard free allowance |
|---|---|---|
| Stored releases plus reserved uploads | 2,000,000,000 bytes total | 10 GB-month per month |
| Class A operations | 10,000 per UTC calendar month | 1 million per month |
| Class B operations | 100,000 per UTC calendar month | 10 million per month |
| Individual file | 250,000,000 bytes | Application policy |

Conditional SQL claims prevent concurrent requests from crossing the ceilings.
Every paid-class R2 call is counted before it runs, including calls that later fail.
D1 accounting failures stop the request. Monthly operation counters reset by UTC month; even a billing window spanning two calendar months stays far below the free allowance.
Storage reservations NEVER reset automatically, including after failed uploads, lifecycle expiry or month changes. This deliberately overcounts storage.
Part indices and exact byte counts must match the reservation; retries cannot upload extra parts or larger bodies.
At a cutoff, requests return 429 and updates pause. There is no paid fallback. Existing releases remain available at the storage cutoff, subject to the read cutoff.
After enough releases fill the 2 GB reservation budget, audit completed objects and pending uploads before any cleanup/accounting adjustment; never reset the ledger blindly.
The private GET /api/releases/usage endpoint exposes the application limits and reserved usage.
Full downloads and HEAD responses use HTTP 200 even if R2 includes full-object range metadata; only explicit GET Range requests use 206. Android requires 200 for its complete APK download.

These are application safeguards, not a Cloudflare billing cap. They cannot limit unrelated buckets, direct account uploads/downloads, other credentials or another service.
Keep public bucket access disabled and all app release traffic behind this Worker.

| Endpoint | Access | Purpose |
|---|---|---|
| GET /api/releases/latest?platform=android | public | Completed version, build, bytes, digest and download URL |
| GET/HEAD /api/releases/files/releases/... | public | Stream package; GET supports ranges |
| POST /api/releases/upload | private CI token | Start upload with validated metadata |
| PUT /api/releases/upload?key=...&uploadId=...&part=... | private CI token | Upload a bounded part |
| POST /api/releases/complete?key=...&uploadId=... | private CI token | Complete upload and advance manifest |

Without RELEASES, routes return 503 and the app reports that it cannot check for updates; existing features keep working.

References: [R2 pricing](https://developers.cloudflare.com/r2/pricing/), [spending-control scope](https://developers.cloudflare.com/billing/manage/spend-management/), [Cloudflare R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/), [Android installation permission](https://developer.android.com/reference/android/content/pm/PackageManager#canRequestPackageInstalls()).
