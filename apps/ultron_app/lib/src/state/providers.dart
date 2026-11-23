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

/// Light by default (the owner's emerald / mint reference); Profile switches to dark or the phone's setting.
final themeModeProvider = NotifierProvider<AppearanceController, ThemeMode>(
  AppearanceController.new,
);

class AppearanceController extends Notifier<ThemeMode> {
  @override
  ThemeMode build() => ThemeMode.light;
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
    if (ref.mounted) ref.invalidate(workspaceProvider);
  }

  void expire() {
    ++_request;
    state = const SessionState(error: 'Your session ended. Sign in again.');
    ref.invalidate(workspaceProvider);
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

/// The live workspace (workflows, runs, approvals, reports, connections) and its actions.
final workspaceProvider =
    AsyncNotifierProvider<WorkspaceController, WorkspaceData>(
      WorkspaceController.new,
    );

class WorkspaceController extends AsyncNotifier<WorkspaceData> {
  final Set<String> _operations = {};

  @override
  Future<WorkspaceData> build() =>
      ref.watch(repositoryProvider).loadWorkspace();

  Future<void> _perform(
    String key,
    Future<WorkspaceData> Function(UltronRepository) operation,
  ) async {
    if (!_operations.add(key)) {
      throw const FrontendException('This request is already in progress.');
    }
    try {
      final data = await operation(ref.read(repositoryProvider));
      if (ref.mounted) state = AsyncData(data);
    } finally {
      _operations.remove(key);
    }
  }

  Future<void> requestRun(String id, {required bool preview}) => _perform(
    'run:$id',
    (repository) => repository.requestRun(id, preview: preview),
  );

  Future<void> decide(String id, ApprovalStatus decision) =>
      _perform('approval:$id', (repository) => repository.decide(id, decision));

  Future<void> sendMessage(String text) =>
      _perform('message', (repository) => repository.sendMessage(text));
}
