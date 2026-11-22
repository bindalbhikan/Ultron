import '../domain/access.dart';
import '../domain/models.dart';

/// What the app asks of the app API (services/app_api). Every call is authorised there; a missing
/// permission comes back as a FrontendException with the server's message.
abstract class AccountRepository {
  AppUser? get currentUser => null;

  /// A public registration: it starts pending until an administrator approves it.
  Future<void> register(String name, String username, String password) async =>
      unavailable();
  Future<AppUser> refreshUser() async => unavailable();
  Future<UserPage> listUsers({String search = '', int page = 0}) async =>
      unavailable();
  Future<List<AccessRole>> listRoles() async => unavailable();
  Future<void> updateUser(
    AppUser user, {
    required String status,
    required String roleId,
  }) async => unavailable();
  Future<void> saveRole({
    required String id,
    required String name,
    required List<String> permissions,
    int? revision,
  }) async => unavailable();

  /// An administrator creates an active account with an approved role; the email is optional.
  Future<AppUser> createUser({
    required String name,
    required String username,
    required String password,
    required String roleId,
    String email = '',
  }) async => unavailable();
  Future<AgentSettings> agentSettings() async => unavailable();
  Future<AgentSettings> saveAgentSettings({
    required String model,
    required String tier,
    required List<String> order,
    required int revision,
  }) async => unavailable();
  Future<AgentMemory> agentMemory({
    String kind = '',
    String search = '',
  }) async => unavailable();
  Future<void> forgetNote(String id) async => unavailable();

  /// The phones in SMS only mode, newest first; an administrator blocks or unblocks one.
  Future<List<SmsPhone>> smsPhones() async => unavailable();
  Future<List<SmsPhone>> blockPhone(
    SmsPhone phone, {
    required bool blocked,
  }) async => unavailable();

  Never unavailable() =>
      throw const FrontendException('This service is not connected.');
}
