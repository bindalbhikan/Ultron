import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../data/cloudflare_repository.dart';
import '../data/repository.dart';
import '../domain/models.dart';

/// The app API (services/app_api). A seller's own build passes theirs with --dart-define=ULTRON_API_URL=...
const appApiUrl = String.fromEnvironment(
  'ULTRON_API_URL',
  defaultValue: 'https://ultron-app-api.bhikan-serein.workers.dev',
);

final repositoryProvider = Provider<UltronRepository>((ref) {
  final repository = CloudflareRepository(
    baseUrl: Uri.parse(appApiUrl),
    onUnauthorized: () {
      Future.microtask(() {
        if (ref.mounted) ref.read(authProvider.notifier).expire();
      });
    },
  );
  ref.onDispose(repository.close);
  return repository;
});

/// Dark by default (the ops look); Profile switches to light or the phone's setting.
final themeModeProvider = NotifierProvider<AppearanceController, ThemeMode>(
  AppearanceController.new,
);

class AppearanceController extends Notifier<ThemeMode> {
  @override
  ThemeMode build() => ThemeMode.dark;
  void set(ThemeMode value) => state = value;
}

final authProvider = NotifierProvider<AuthController, SessionState>(
  AuthController.new,
);

class AuthController extends Notifier<SessionState> {
  int _request = 0;

  @override
  SessionState build() => const SessionState();

  Future<void> signIn(String username, String password) async {
    if (state.busy) return;
    final request = ++_request;
    state = const SessionState(busy: true);
    try {
      await ref.read(repositoryProvider).signIn(username, password);
      if (!ref.mounted || request != _request) return;
      state = SessionState(
        phase: SessionPhase.signedIn,
        user: ref.read(repositoryProvider).currentUser,
      );
    } on FrontendException catch (error) {
      if (ref.mounted && request == _request) {
        state = SessionState(error: error.message);
      }
    } catch (_) {
      if (ref.mounted && request == _request) {
        state = const SessionState(
          error: 'Sign-in could not finish. Try again.',
        );
      }
    }
  }

  Future<void> signOut() async {
    ++_request;
    state = const SessionState();
    await ref.read(repositoryProvider).signOut();
  }

  void expire() {
    ++_request;
    state = const SessionState(error: 'Your session ended. Sign in again.');
  }

  Future<void> refreshAccess() async {
    if (state.phase != SessionPhase.signedIn || state.busy) return;
    final request = ++_request;
    final previous = state.user;
    state = SessionState(
      phase: SessionPhase.signedIn,
      user: previous,
      busy: true,
    );
    try {
      final user = await ref.read(repositoryProvider).refreshUser();
      if (ref.mounted && request == _request) {
        state = SessionState(phase: SessionPhase.signedIn, user: user);
      }
    } on FrontendException catch (error) {
      if (ref.mounted && request == _request) {
        state = SessionState(
          phase: SessionPhase.signedIn,
          user: previous,
          error: error.message,
        );
      }
    }
  }
}

bool canAccess(WidgetRef ref, String permission) =>
    ref.watch(authProvider).user?.allows(permission) ?? false;
