# 12. url_launcher for update downloads

Status: added 24 Nov 2026, version 6.3.3, with platform implementations locked in pubspec.lock.
The Flutter team's maintained BSD-licensed plugin opens desktop update packages in the system browser.
It supports the native platforms without shell commands or separate launchers. Report calculations are untouched.
Android APK updates use the existing Kotlin bridge and AndroidX FileProvider.
Validation: Flutter analysis, widget tests and web compilation; native download/install still needs a device.
