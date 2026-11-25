import '../domain/access.dart';
import '../domain/models.dart';
import 'account_repository.dart';

/// The app's boundary to its server: sign-in by username, the live workspace (workflows, runs, approvals,
/// reports, connections) and its actions, plus everything in [AccountRepository].
abstract class UltronRepository extends AccountRepository {
  Future<void> signIn(String username, String password);
  Future<void> signOut();

  /// The session kept on the device from an earlier run, or null: sign in.
  Future<AppUser?> restoreSession() async => null;
  Future<WorkspaceData> loadWorkspace() async => unavailable();
  Future<WorkspaceData> requestRun(
    String workflowId, {
    required bool preview,
    Map<String, String> inputs = const {},
  }) async => unavailable();
  Future<Map<String, dynamic>> control(
    String operation, {
    Map<String, Object?> args = const {},
    bool preview = false,
    bool confirmed = false,
  }) async => unavailable();
  Future<WorkspaceData> decide(String id, ApprovalStatus decision) async =>
      unavailable();
  Future<WorkspaceData> sendMessage(String text) async => unavailable();
}
