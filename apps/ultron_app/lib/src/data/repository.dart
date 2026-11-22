import 'account_repository.dart';

/// The app's boundary to its server: sign-in by username plus everything in [AccountRepository].
abstract class UltronRepository extends AccountRepository {
  Future<void> signIn(String username, String password);
  Future<void> signOut();
}
