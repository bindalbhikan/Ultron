import '../domain/models.dart';
import 'account_repository.dart';

/// The frontend boundary. Production implementations must authorise each call.
abstract class UltronRepository extends AccountRepository {
  bool get isDemo;
  Future<String> signIn(String email, String password);
  Future<void> verify(String challenge, String code);
  Future<void> resetPassword(String email);
  Future<void> signOut();
  Future<WorkspaceData> loadWorkspace();
  Future<WorkspaceData> requestRun(String workflowId, {required bool preview});
  Future<WorkspaceData> decide(String id, ApprovalStatus decision);
  Future<WorkspaceData> sendMessage(String text);
}

/// Deliberately fails closed until a supported native-app API is configured.
class UnconfiguredRepository extends UltronRepository {
  @override
  bool get isDemo => false;

  Never _unavailable() => throw const FrontendException(
    'Live access is not configured. Connect an authenticated app backend first.',
  );

  @override
  Future<String> signIn(String email, String password) async => _unavailable();
  @override
  Future<void> verify(String challenge, String code) async => _unavailable();
  @override
  Future<void> resetPassword(String email) async => _unavailable();
  @override
  Future<void> signOut() async {}
  @override
  Future<WorkspaceData> loadWorkspace() async => _unavailable();
  @override
  Future<WorkspaceData> requestRun(
    String workflowId, {
    required bool preview,
  }) async => _unavailable();
  @override
  Future<WorkspaceData> decide(String id, ApprovalStatus decision) async =>
      _unavailable();
  @override
  Future<WorkspaceData> sendMessage(String text) async => _unavailable();
}
