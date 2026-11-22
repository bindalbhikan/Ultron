import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/demo_repository.dart';
import '../data/repository.dart';
import '../data/cloudflare_repository.dart';
import '../domain/models.dart';

const demoMode = bool.fromEnvironment('ULTRON_DEMO', defaultValue: true);
const appApiUrl = String.fromEnvironment('ULTRON_API_URL');

final repositoryProvider = Provider<UltronRepository>((ref) {
  if (demoMode) return DemoRepository();
  if (appApiUrl.isEmpty) return UnconfiguredRepository();
  final repository = CloudflareRepository(baseUrl: Uri.parse(appApiUrl), onUnauthorized: () {
    Future.microtask(() { if (ref.mounted) ref.read(authProvider.notifier).expire(); });
  });
  ref.onDispose(repository.close);
  return repository;
});

final themeModeProvider = NotifierProvider<AppearanceController, ThemeMode>(
  AppearanceController.new,
);

class AppearanceController extends Notifier<ThemeMode> {
  @override
  ThemeMode build() => ThemeMode.system;
  void set(ThemeMode value) => state = value;
}

final authProvider = NotifierProvider<AuthController, SessionState>(
  AuthController.new,
);

class AuthController extends Notifier<SessionState> {
  int _request = 0;

  @override
  SessionState build() => const SessionState();

  Future<void> signIn(String email, String password) async {
    if (state.busy) return;
    final request = ++_request;
    state = const SessionState(busy: true);
    try {
      final challenge = await ref
          .read(repositoryProvider)
          .signIn(email, password);
      if (!ref.mounted || request != _request) return;
      final user = ref.read(repositoryProvider).currentUser;
      state = SessionState(phase: user == null ? SessionPhase.verification : SessionPhase.signedIn,
        challenge: user == null ? challenge : null, user: user);
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

  Future<void> verify(String code) async {
    final challenge = state.challenge;
    if (state.busy || challenge == null) return;
    final request = ++_request;
    state = SessionState(
      phase: SessionPhase.verification,
      challenge: challenge,
      busy: true,
    );
    try {
      await ref.read(repositoryProvider).verify(challenge, code);
      if (!ref.mounted || request != _request) return;
      state = SessionState(phase: SessionPhase.signedIn, user: ref.read(repositoryProvider).currentUser);
    } on FrontendException catch (error) {
      if (ref.mounted && request == _request) {
        state = SessionState(
          phase: SessionPhase.verification,
          challenge: challenge,
          error: error.message,
        );
      }
    } catch (_) {
      if (ref.mounted && request == _request) {
        state = SessionState(
          phase: SessionPhase.verification,
          challenge: challenge,
          error: 'Verification could not finish. Try again.',
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

  void expire() { ++_request; state = const SessionState(error: 'Your session ended. Sign in again.'); ref.invalidate(workspaceProvider); }

  Future<void> refreshAccess() async {
    if (state.phase != SessionPhase.signedIn || state.busy) return;
    final request=++_request;
    final previous=state.user;
    state=SessionState(phase:SessionPhase.signedIn,user:previous,busy:true);
    try {
      final user=await ref.read(repositoryProvider).refreshUser();
      if (ref.mounted && request==_request) state=SessionState(phase:SessionPhase.signedIn,user:user);
    } on FrontendException catch(error) {
      if (ref.mounted && request==_request) state=SessionState(phase:SessionPhase.signedIn,user:previous,error:error.message);
    }
  }
}

bool canAccess(WidgetRef ref, String permission) => ref.watch(authProvider).user?.allows(permission) ?? false;

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

/// Local presentation preferences only. No Android service is started here.
class PhonePreferences {
  const PhonePreferences({
    this.agent = false,
    this.sms = false,
    this.sim = 'Both SIMs',
    this.senders = '',
  });
  final bool agent;
  final bool sms;
  final String sim;
  final String senders;

  PhonePreferences copyWith({
    bool? agent,
    bool? sms,
    String? sim,
    String? senders,
  }) => PhonePreferences(
    agent: agent ?? this.agent,
    sms: sms ?? this.sms,
    sim: sim ?? this.sim,
    senders: senders ?? this.senders,
  );
}

final phonePreferencesProvider =
    NotifierProvider<PhonePreferencesController, PhonePreferences>(
      PhonePreferencesController.new,
    );

class PhonePreferencesController extends Notifier<PhonePreferences> {
  @override
  PhonePreferences build() => const PhonePreferences();
  void update(PhonePreferences value) => state = value;
}
