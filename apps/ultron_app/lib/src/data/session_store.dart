import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// The signed-in session kept on the device, so closing the app does not sign the user out: the app API's
/// bearer token and the user as /api/me last sent it (shown at once on the next start, then checked again).
abstract class SessionStore {
  const SessionStore();
  Future<({String token, Map<String, dynamic> user})?> read();
  Future<void> save(String token, Map<String, dynamic> user);
  Future<void> clear();
}

/// The OS key store (Android Keystore, Windows Credential Manager, the macOS keychain, libsecret on Linux).
/// A device whose key store fails only loses "stay signed in"; signing in still works.
class SecureSessionStore extends SessionStore {
  const SecureSessionStore();

  // macOS: the legacy keychain, which needs no keychain-sharing entitlement (so no provisioning profile)
  static const _storage = FlutterSecureStorage(
    mOptions: MacOsOptions(usesDataProtectionKeychain: false),
  );
  static const _tokenKey = 'ultron_session_token';
  static const _userKey = 'ultron_session_user';

  @override
  Future<({String token, Map<String, dynamic> user})?> read() async {
    try {
      final token = await _storage.read(key: _tokenKey);
      final user = await _storage.read(key: _userKey);
      if (token == null || token.isEmpty || user == null) return null;
      final decoded = jsonDecode(user);
      if (decoded is! Map<String, dynamic>) return null;
      return (token: token, user: decoded);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> save(String token, Map<String, dynamic> user) async {
    try {
      await _storage.write(key: _tokenKey, value: token);
      await _storage.write(key: _userKey, value: jsonEncode(user));
    } catch (_) {
      // not kept: the next start asks to sign in
    }
  }

  @override
  Future<void> clear() async {
    try {
      await _storage.delete(key: _tokenKey);
      await _storage.delete(key: _userKey);
    } catch (_) {
      // nothing kept to clear
    }
  }
}

/// Keeps the session for this run only (tests, and a repository built without a store).
class MemorySessionStore extends SessionStore {
  MemorySessionStore();
  ({String token, Map<String, dynamic> user})? saved;

  @override
  Future<({String token, Map<String, dynamic> user})?> read() async => saved;

  @override
  Future<void> save(String token, Map<String, dynamic> user) async =>
      saved = (token: token, user: user);

  @override
  Future<void> clear() async => saved = null;
}
