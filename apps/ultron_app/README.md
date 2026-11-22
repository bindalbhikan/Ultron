# Ultron app

Emerald Flutter frontend for Android, iOS, Windows and macOS, with a web runner for local previews. Developed by **Bhikan Deshmukh**, credited in the login footer and Profile → About Ultron.

## Toolchain

Flutter **3.50.0 stable** and bundled Dart **3.14.0**, verified from the installed SDK and [official releases](https://docs.flutter.dev/release/release-notes). The SDK is pinned in `.flutter-version`; dependencies are locked in `pubspec.lock`. Keep CI, SDK constraints and `AppInfo` in sync when upgrading. Material widgets use the current `material_ui` package.

## Run

From this directory with Flutter on PATH:

```powershell
flutter pub get
flutter run -d windows
# Interactive browser preview without native build tools:
flutter run -d web-server --web-hostname 127.0.0.1 --web-port 8788
```

On the owner's PC, the helper also finds the SDK installed under the local `.ultron/tools` folder:

```powershell
./tool/dev.ps1 preview
./tool/dev.ps1 analyze
./tool/dev.ps1 test
```

Use the helper for builds/previews from Google Drive: it copies source into a fresh local `.ultron/build/` workspace, excludes `desktop.ini` and generated caches, then resolves the locked dependencies. This avoids Drive sync races while Flutter copies web assets. The source stays on Drive; restart the helper after editing it. Direct commands above are suitable for an ordinary local checkout.

Android needs an emulator/device and Android toolchain. Windows needs the Visual Studio C++ desktop workload. iOS/macOS need a Mac and Xcode. Their native binaries cannot be validated on this Windows host. The new app does not reuse the installed Phone app's identity/signing key.

## Demo sign-in

Select **Fill demo account**, then sign in and verify:

- Email: `owner@example.com`
- Password: `ultron-demo`
- Verification code: `123456`

These are public examples for an in-memory demo, not production credentials. Do not enter real credentials. Protected routes require verification; sign-out clears the session and demo records. No passwords, codes or messages are written to disk or logs. Reset requests, decisions, run requests and agent answers are simulated. Missing sources are excluded and named, never shown as zero.

`--dart-define=ULTRON_DEMO=false` selects a fail-closed live placeholder: no authentication or workspace access is available until a supported backend is connected. It never falls back to demo access. Never bundle portal cookies, shared dashboard/GitHub tokens or service-account keys in this app.

## Frontend

Login, verification, reset form, Home, Agent, searchable/filterable Workflows, Reports with source coverage, approval review, Analytics, Connections, Schedule, Profile, appearance, About and sign-out. Mobile uses bottom navigation; wider windows use a rail/sidebar and expanded overview. Local DM Sans, light/dark themes and common components form one design system.

Home totals are derived from demo runs. Analytics and schedule examples are labelled illustrative. Live progress and schedules must come from backend sources. File access, portal reconnect and push delivery explain their unconnected status when selected.

**Phone Work** includes agent-mode settings/status, SMS sync, SIM/sender filters, permission setup, test/import entry points, courier OTP/POD status and device setup. Controls are presentation/demo preferences: no permission is requested, SMS read or service started. Unknown device/queue values stay unavailable. Android migration and parity checks must finish before discontinuing `../../android app/`; see [migration map](../../docs/apps/ultron-app.md).

## Source and checks

`lib/src/domain/` defines immutable records; `data/` defines the repository and demo/live boundaries; `state/` contains Riverpod controllers; `theme/` and `ui/` own the design and screens. `router.dart` guards protected routes. `app_info.dart` centralises versions and developer credits.

```powershell
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
flutter build web --release
```

The frontend workflow runs these checks on app changes. It is infrastructure, not a scheduled working, and deploys nothing. Native runtime validation requires the actual platform toolchains/devices. Font licence: `assets/fonts/OFL.txt`, also registered in About → Licences.
