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

## Sign in

The app talks to the live app API (`../../services/app_api`, `--dart-define=ULTRON_API_URL=...` for another
seller's). There is no demo. Accounts sign in with a username and a password of 8+ characters; a new registration
waits until an administrator approves it on **Users**. The first administrator is made from the owner's terminal:
`.venv\Scripts\python scriptspp\create_admin.py` (the password is typed hidden, never stored or logged).

## Screens

Home (live numbers), Control (agent model, SMS phones, Agent mode phones, memory), Users (approve, create),
Roles, Profile; and without an account, **SMS only** (Android). A role sees only its screens. See
[the app's doc](../../docs/apps/ultron-app.md) for what each needs.

## Android: SMS only and Agent mode

`android/app/src/main/kotlin/.../sms` sends every SMS of the chosen SIM to the SMS sheet through the worker
(no setup on the phone). `.../agent` is Agent mode: the phone looks up Myntra styles for the zero TD bot when the
office PC is off; an administrator turns it on from the phone (Control → Agent mode), which gets its own token
from the app API, and revokes it there. Both keep running in the background and after a reboot. They replace
the old Kotlin Ultron Phone app (removed 23 Nov 2026): uninstall that app once this one runs.

## Source and checks

`lib/src/domain/` defines immutable records; `data/` holds the live repository and the Android bridges; `state/` contains Riverpod controllers; `theme/` and `ui/` own the design and screens. `router.dart` guards protected routes. `app_info.dart` centralises versions and developer credits.

```powershell
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
flutter build web --release
```

The frontend workflow runs these checks on app changes. It is infrastructure, not a scheduled working, and deploys nothing. Native runtime validation requires the actual platform toolchains/devices. Font licence: `assets/fonts/OFL.txt`, also registered in About → Licences.
