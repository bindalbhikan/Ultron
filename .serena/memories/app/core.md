# App boundaries
- apps/ultron_app is the current Flutter app; retired root android app was removed. Native Android SMS and Agent mode now live under Flutter app Android Kotlin sources.
- lib/src/domain immutable records, data live CloudflareRepository and Android bridges, state Riverpod, theme/ui design; router guards routes, app_info centralizes versions.
- Signed-in user stays signed in using device key store and 30-day server session; signed-in users never see SMS only. SMS only applies to unsigned phones and opens automatically when enabled.
- Android SMS only and Agent mode continue in background/after reboot through KeepAlive.kt and related services. Agent mode uses revocable phone token from app API and existing Myntra phone lookup exception.
- UI authorization is backed by server checks. No demo login, sample records or credentials in app. Preserve emerald/mint design specified in docs/apps/ultron-app.md.
- Read docs/apps/ultron-app.md and apps/ultron_app/README.md for feature requirements; commands in `mem:suggested_commands`, service boundaries in `mem:services/core`.
