import '../domain/access.dart';
import '../domain/models.dart';

/// What the app asks of the app API (services/app_api). Every call is authorised there; a missing
/// permission comes back as a FrontendException with the server's message.
abstract class AccountRepository {
  AppUser? get currentUser => null;

  /// First-time setup: true while no administrator exists yet.
  Future<bool> setupNeeded() async => false;

  /// Makes the first administrator with the one-time setup code; the person chooses their own password.
  Future<void> firstAdmin({
    required String code,
    required String name,
    required String username,
    required String password,
  }) async => unavailable();

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

  /// Agent mode phones: list; make a token for this phone (returned once); revoke one.
  Future<List<PhoneAgent>> phoneAgents() async => unavailable();
  Future<String> newPhoneAgent(String device) async => unavailable();
  Future<List<PhoneAgent>> revokePhoneAgent(String id) async => unavailable();

  /// The agent's model API keys: several per provider, used in turn (the next when one hits its limit).
  Future<List<ApiKey>> apiKeys() async => unavailable();
  Future<List<ApiKey>> addApiKey({
    required String provider,
    required String key,
    String label = '',
  }) async => unavailable();
  Future<List<ApiKey>> removeApiKey(String id) async => unavailable();
  Future<List<ApiKey>> changeApiKey(
    String id, {
    String? move,
    bool reset = false,
  }) async => unavailable();

  /// provider -> the model ids the agent last read from it.
  Future<Map<String, List<String>>> agentModels() async => unavailable();

  Never unavailable() =>
      throw const FrontendException('This service is not connected.');
}
