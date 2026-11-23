import '../domain/models.dart';
import 'account_repository.dart';

/// The app's boundary to its server: sign-in by username, the live workspace (workflows, runs, approvals,
/// reports, connections) and its actions, plus everything in [AccountRepository].
abstract class UltronRepository extends AccountRepository {
  Future<void> signIn(String username, String password);
  Future<void> signOut();
  Future<WorkspaceData> loadWorkspace() async => unavailable();
  Future<WorkspaceData> requestRun(
    String workflowId, {
    required bool preview,
  }) async => unavailable();
  Future<WorkspaceData> decide(String id, ApprovalStatus decision) async =>
      unavailable();
  Future<WorkspaceData> sendMessage(String text) async => unavailable();
}
