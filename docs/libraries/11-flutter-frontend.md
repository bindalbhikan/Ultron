# 11 — Flutter frontend libraries

**Status:** added for `apps/ultron_app/`. New frontend only; existing Python workings and report outputs are unchanged.

| Choice | Purpose |
|---|---|
| Flutter 3.50.0 / Dart 3.14.0 | Verified stable SDK; native platform runner sources and web preview; pinned in `.flutter-version` and CI |
| `material_ui` 1.11.1 | Current Material implementation; Flutter 3.50 deprecates the old Material umbrella import |
| `flutter_riverpod` 3.5.0 | Typed state, async workspace data, repository injection and isolated tests |
| `go_router` 18.1.4 | Declarative route guards, direct links and shared app shell |
| `lucide_icons_flutter` 4.0.3 | Coherent bundled line icons; no runtime icon fetch |
| `flutter_lints` 6.0.0 / Flutter tests | Analysis and state/responsive widget validation |
| Bundled DM Sans | Offline type; OFL retained in assets and registered in About licences |

No paid components, chart SDK, runtime font fetch, analytics service, native credential plugin or HTTP client is introduced. Simple analytics use accessible Flutter widgets. Auth/API and Android service migration need separate dependency decisions once contracts are specified. Direct releases were checked on pub.dev; the complete graph is locked. SDK-pinned transitive versions must not be forcibly upgraded.

References: [Flutter releases](https://docs.flutter.dev/release/release-notes), [Material UI](https://pub.dev/packages/material_ui), [Riverpod](https://pub.dev/packages/flutter_riverpod), [GoRouter](https://pub.dev/packages/go_router), [Lucide](https://pub.dev/packages/lucide_icons_flutter).
