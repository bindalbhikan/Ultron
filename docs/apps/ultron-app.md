# Ultron app — cross-platform frontend

**Status:** 23 Nov 2026: live. The app talks to the deployed app API (`docs/apps/app-api.md`); the demo
(sample data, demo sign-in, the verification code) is removed. The old Kotlin `android app/` (Ultron Phone) is
removed too: its SMS and Agent mode are in this app (`android/.../sms`, `.../agent`).

## What it has

Every screen reads a live service; a person sees only what their role allows (`domain/access.dart`):

| Screen | Path | Needs | What |
|---|---|---|---|
| Sign in | `/login` | none | username and password (8+ characters); no SMS OTP (paid), no demo |
| First-time setup | `/setup` | the setup code | only while no administrator exists: makes the first one, who chooses their own password, then signs in |
| Ask for an account | `/register` | none | name, username, password; waits as *pending* until an administrator approves |
| SMS only | `/sms` | none | Android: a name and a SIM, then every SMS goes to the sheet (below) |
| Waiting for approval | `/access` | signed in | a pending or disabled account; "Check again" re-reads the access |
| Home | `/app/home` | `app.access` | live numbers: registrations waiting, SMS phones (last SMS, sent), agent model, memory notes; a number that could not be read shows "—" and why, never 0 |
| Control | `/app/control` | `agent.tools.read` | **Brain**: the model (auto, or a provider and one of its models from a list), the API keys (add several per provider, order, retry, remove; each shows Ready / Limit · back HH:MM / Refused), tier, provider order; the SMS phones (block / unblock), Agent mode (turn this phone on, revoke a phone), the memory (remove a note) |
| Users | `/app/admin` | `users.manage` | search, **Approve** on a pending registration, change role / status, **Create user** (username, optional email) |
| Roles | `/app/roles` | `roles.manage` | roles and their permissions |
| Profile | `/app/profile` | `app.access` | role, permissions, appearance (dark / light / phone), sign out |

Phones show at most five items in the bottom bar; wider screens get a side rail.

## Design (23 Nov 2026)

The UI was reviewed with the ui-ux-pro-max skill (global skill, `~/.claude/skills/ui-ux-pro-max`) and rebuilt
on its design system for an ops / admin product: a **dark operations look** (slate `#0F172A` surfaces, status
green `#22C55E`), with a light variant of the same roles (green `#15803D` on white for 5:1 contrast). DM Sans
(bundled, OFL) stays the font. Rules applied: body text 14-16px, 48dp touch targets, labels on every field,
errors next to the form with an icon (never colour alone), status words with a dot, tabular numbers, safe
areas. `test/app_test.dart` checks every screen at 320, 390, 760 and 1440px in dark and light without overflow.

Flutter 3.50.0 stable and bundled Dart 3.14.0, pinned. Android, iOS, Windows, macOS and Linux runners; web for
local previews. `--dart-define=ULTRON_API_URL=...` points another seller's build at their own API.

## Data and access boundaries

`CloudflareRepository` is the only repository: every call is authorised by the server, and the session token
lives in memory (closing the app asks to sign in again). Telegram chat access and dashboard cookies do not sign
in to this app. No secret is built into the app: the SMS sheet's link and key stay on the worker.

## Phone Work migration map

| Existing component | New app responsibility | Current status |
|---|---|---|
| `AgentService.kt`, `MyntraLookup.kt` | Foreground service, worker polling, job/result protocol, check-ins | ✅ 23 Nov 2026: `agent/AgentService`, `MyntraLookup`; a token per phone from the app API (Control → Agent mode), revocable |
| `SmsReceiver.kt`, `UploadWorker.kt` | Incoming SMS, offline retry, deduplication, SIM selection | ✅ 22 Nov 2026: `sms/SmsReceiver`, `SmsUpload` (through the worker; no sender filter: every SMS of the SIM) |
| `SmsImport.kt` | Explicit 60-day inbox import and duplicate rules | ✅ `sms/SmsImport` ("Send old SMS") |
| `Pod.kt`, `apps-script/Code.gs` | Expiring POD fetch, AWB extraction, per-portal OTP replacement, evidence retention | ✅ `sms/Pod`; Code.gs v17 (User column, `Agent · <name>`) |
| `BootReceiver.kt`, `Prefs.kt`, manifest | Reboot resume, battery/autostart and authorised settings | ✅ `sms/SmsService`, `SmsBootReceiver`, `SmsPrefs` |

On-device SMS/foreground work is Android-specific. Other platforms may manage connected-device status through a future backend; they must not claim local Android capabilities. Raw SMS, OTPs, customer data and session values must stay out of public source, logs and fixtures.

Before discontinuing the old app, check equivalent results for lookups, duplicate prevention, SIM/sender filtering, offline retry, POD capture, OTP replacement and reboot recovery. Plan app identity/signing, settings transfer, rollback and duplicate-service prevention. App sign-out is separate from marketplace logout; never log out of Myntra or automate CAPTCHA.

## Validation

The Windows helper stages builds/previews outside Google Drive under the user's local `.ultron/build/` directory, excluding `desktop.ini` and generated caches. Drive injected a disappearing `desktop.ini` into the first web asset copy; a local build avoids that race. Source remains in the checkout.

Checks cover verification/route guards, sign-out, developer credits, source coverage, expired/already-decided approvals, fail-closed live mode, mobile/desktop layouts and large text. CI runs format, analysis, tests and web compilation on app changes and deploys nothing. It is excluded from bot command/watch checks by docs sync. Native runtime checks require actual native toolchains/devices; widget/web checks alone do not establish that behaviour.

Local validation passed: formatting, Flutter analysis, 15 repository/widget tests and a release web build. The approved browser opened the built assets, completed demo sign-in/verification and rendered desktop/mobile dashboards without page errors.

## Control panel and accounts (22 Nov 2026)

* **Control panel** (`ui/control_screen.dart`, needs `agent.tools.read`) shows and sets the agent's model:
  auto-select on or off (then one `provider:model` tried first), smart or fast tier, and the providers in
  the order they are tried (drag to reorder, switch one off). Saving needs `agent.manage`. It also lists the
  agent's memory by kind with a search; an administrator (`memory.manage`) removes a note. What is saved
  reaches the agent within 5 minutes (`docs/bots/agent-models.md`).
* **Create user** (Users page, `users.manage`) makes an active account with a first password and an
  approved role. The person should change the password after signing in. Public registration still
  starts pending.
* `CloudflareRepository` calls `/api/admin/users` (POST), `/api/agent/settings` (GET / PUT, with the revision)
  and `/api/agent/memory` (GET, DELETE); `test/control_test.dart` covers them. The demo repository answers
  "This service is not connected" for these.
* Flutter 3.50.0 is installed on the owner's PC at `%USERPROFILE%\.ultron\tools\flutter`, on the user PATH,lutter`, on the user PATH,
  checksum-verified; `tool/dev.ps1 analyze` / `test` find it there.

## Builds and downloads (22 Nov 2026)

**Installs over the old Ultron Phone app (23 Nov 2026).** The Android app id is the old app's
(`com.bindal.ultronphone`) and the signing key is the same, and the version code continues after it
(`1<run number>`, the old one stopped at 23). A phone that had the old app takes ULTRON as its update: no
uninstall, and Play Protect sees the app it already knew rather than a new unknown one asking for SMS. The Kotlin
code keeps its own package (`com.ultron.ultron_app`). A phone without the old app may still be stopped by Play
Protect's fraud protection (an SMS permission from a link): only an install from Google Play avoids that.

The app is called **ULTRON** everywhere a person sees it: the Android launcher, the window titles, `ULTRON.exe`,
`ULTRON.app`, the Linux binary and the web title.

`.github/workflows/flutter-app.yml` runs on every change to `apps/ultron_app/`:

1. `frontend`: format, analyze, tests and a web build.
2. Four builds in parallel on GitHub's runners:

   | Job | Runner | Download file |
   |---|---|---|
   | `android` | Ubuntu | `ULTRON.apk` |
   | `windows` | Windows | `ULTRON-Windows.zip` (run `ULTRON.exe`) |
   | `macos` | macOS | `ULTRON-macOS.zip` (`ULTRON.app`, unsigned: right-click, Open the first time) |
   | `linux` | Ubuntu, GTK 3 | `ULTRON-Linux.tar.gz` (run `bundle/ULTRON`) |

   The APK is signed with the fixed key of Ultron Phone, kept in Drive AGENT WORK/ULTRON PHONE
   (`scripts/github/android_app.py keystore`). So every new APK installs over the one on the phone.
3. `publish` (main only): `scripts/github/flutter_app.py publish` puts the files in Drive **AGENT WORK/ULTRON APP**,
   each updated in place under its fixed name. Telegram then gets one note with the download links. A platform
   whose build failed is named "not built this time" and never silently left out.

Version: `0.1.<run number>`, the run number is also the Android version code.

## SMS only mode (22 Nov 2026)

The sign-in screen's **SMS only (no account)** opens `/sms` (`ui/sms_only_screen.dart`). There the person types a
name (2-40 characters) and picks Both / SIM 1 / SIM 2, then taps Start. The app asks for SMS (and, on Android 13+,
notification) permission. From then on, every SMS that phone receives goes to the SMS sheet with that name. It keeps
working after the app is closed and after a reboot.

How it works on the Android side (`android/app/src/main/kotlin/.../sms`, ported from `android app/`):

* `SmsReceiver` queues each SMS of the chosen SIM. `SmsUpload` (WorkManager: retries, backoff, waits for the
  network) fetches the POD of a courier SMS (`Pod`, PDFBox) and posts JSON to the worker's `POST /api/sms`.
* `SmsService` is a foreground service ("ULTRON: SMS to sheet on") that keeps the process alive on phones that
  kill idle apps. `SmsBootReceiver` starts it again after a reboot or an update.
* **Internet off**: an SMS waits on the phone until the network is back (also across reboots) and is then
  sent; on any network or server trouble it tries again with growing pauses (up to 5 hours apart) and never gives
  up. Only the worker's own refusal stops it: 403 (phone blocked) or 400 (bad request). Agent mode checks in every
  minute while offline, and keeps sending a finished job's answers for up to 6 hours.
* `SmsImport` sends the inbox of the last 60 days on a tap. The sheet skips SMS it already has.
* `MainActivity`'s `ultron/sms` channel (`lib/src/data/sms_bridge.dart`) handles status, start, stop,
  permissions, battery and the old SMS.

The phone keeps its random id and the name. It never holds the sheet's link or key: the worker holds them.
`--dart-define=ULTRON_WORKER=...` points another seller's build at their own worker. A phone blocked in the
control panel gets "this phone is blocked" in its activity log.
