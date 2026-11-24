# App updates through Cloudflare

Status (24 Nov 2026): implementation added; live R2 storage awaits account activation (Cloudflare error 10042).
The other app fixes deploy independently. Do not report R2 publication as working until a real package is uploaded and downloaded.

The app checks the public app API at startup and offers a newer build inside every screen, including SMS only.
Profile also provides Check for updates. Version and build come from CI through Dart defines.

Android streams the APK into private cache, checks byte count, SHA-256, package id and a strictly newer version code, then opens Android's installer.
The user allows ULTRON as an installation source once and confirms each installation. Android enforces the signing key; CI uses the existing Ultron Phone key.
Desktop updates open the Cloudflare download in the system browser; the user opens the package. No silent desktop replacement. iOS and web do not advertise native updates.
Old installations need the first updated package installed from Drive once to gain the updater.

## Storage and publication

Enable R2 in the Cloudflare dashboard, create bucket ultron-app-releases, then add this top-level binding to services/app_api/wrangler.jsonc and deploy:
'r2_buckets': [{ 'binding': 'RELEASES', 'bucket_name': 'ultron-app-releases' }] (use JSON double quotes).
No account billing activation is performed by the agent.
Migration 0009_app_release.sql keeps the current completed build per platform. Its conditional update prevents an older CI run from replacing a newer release.

CI retains the Drive packages, then scripts/github/app_updates.py uploads successful packages in 10 MB multipart chunks through the app API.
APP_UPDATES_API is the public app API origin; DASHBOARD_TOKEN is the existing private CI credential, matching the app API WORKER_TOKEN.
Credentials and Drive links are not printed. The manifest advances after the multipart upload completes and its size matches.
Failed uploads fail publication explicitly and preserve the previous manifest. Missing platform builds never create a new manifest.
R2 keys contain build, platform and SHA-256.

| Endpoint | Access | Purpose |
|---|---|---|
| GET /api/releases/latest?platform=android | public | Completed version, build, bytes, digest and download URL |
| GET/HEAD /api/releases/files/releases/... | public | Stream package; GET supports ranges |
| POST /api/releases/upload | private CI token | Start upload with validated metadata |
| PUT /api/releases/upload?key=...&uploadId=...&part=... | private CI token | Upload a bounded part |
| POST /api/releases/complete?key=...&uploadId=... | private CI token | Complete upload and advance manifest |

Without RELEASES, routes return 503 and the app reports that it cannot check for updates; existing features keep working.

References: [Cloudflare R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/), [Android installation permission](https://developer.android.com/reference/android/content/pm/PackageManager#canRequestPackageInstalls()).
