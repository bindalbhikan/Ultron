import '../domain/access.dart';
import '../domain/models.dart';

abstract class AccountRepository {
  AppUser? get currentUser => null;
  Future<void> register(String name, String email, String password) async => unavailable();
  Future<AppUser> refreshUser() async => unavailable();
  Future<UserPage> listUsers({String search = '', int page = 0}) async => unavailable();
  Future<List<AccessRole>> listRoles() async => unavailable();
  Future<void> updateUser(AppUser user, {required String status, required String roleId}) async => unavailable();
  Future<void> saveRole({required String id, required String name, required List<String> permissions, int? revision}) async => unavailable();
  Never unavailable() => throw const FrontendException('This service is not connected.');
}
