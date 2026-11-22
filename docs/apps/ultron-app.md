# Ultron app — cross-platform frontend

**Status:** Flutter frontend built in `apps/ultron_app/`. 22 Nov 2026: the **Control panel** (`/app/control`) and **Create user** (Users page) work against the app API (`docs/apps/app-api.md`). That API is tested but not deployed yet; the Android Phone service migration remains open. The Kotlin `android app/` remains active until its background work is migrated and verified.

## Product and toolchain

The frontend follows the owner's emerald/mint reference. It includes required login, verification, reset form, guarded routes, Home, Agent, Workflows, Reports, Approvals, Analytics, Connections, Schedule, Profile and Phone Work. The login footer and Profile → About Ultron show **Developed by Bhikan Deshmukh**.

Flutter 3.50.0 stable and bundled Dart 3.14.0 were verified from the installed SDK and are pinned for this implementation. Android, iOS, Windows and macOS runner sources are included; web provides a local interactive preview. Native builds still require their platform toolchains. See the app README and `docs/libraries/11-flutter-frontend.md`.

## Data and access boundaries

`UltronRepository` defines authentication, workspace, run, approval and chat contracts. `DemoRepository` contains synthetic fixtures and in-memory mutations. Protected demo operations check their session; decisions check pending state and expiry. UI submission is guarded. These frontend/demo checks do not replace server authorisation.

`ULTRON_DEMO=false` fails closed without data or demo sign-in. A supported app API is needed before live access. Telegram allowed-chat access and dashboard cookies do not automatically authenticate this app. Native secrets must use a supported secure store and server flow, never assets/build defines.

Missing report sources stay named and excluded. Missing device health/check-ins/queue counts are unavailable, never zero. Analytics and schedule are marked illustrative; live schedules must come from the canonical worker. No real portal, workbook, stock, price, ticket, customer or courier is changed by the frontend.

## Phone Work migration map

| Existing component | New app responsibility | Current status |
|---|---|---|
| `AgentService.kt`, `MyntraLookup.kt` | Foreground service, worker polling, job/result protocol, check-ins | Setup/status UI built; Android runtime pending |
| `SmsReceiver.kt`, `UploadWorker.kt` | Incoming SMS, offline retry, deduplication, SIM/sender selection | Setup UI built; no permissions requested or SMS read |
| `SmsImport.kt` | Explicit 60-day inbox import and duplicate rules | Frontend entry point; native implementation pending |
| `Pod.kt`, `apps-script/Code.gs` | Expiring POD fetch, AWB extraction, per-portal OTP replacement, evidence retention | Status/log entry points built; processing pending |
| `BootReceiver.kt`, `Prefs.kt`, manifest | Reboot resume, battery/autostart and authorised settings | Setup UI built; lifecycle/storage migration pending |

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
