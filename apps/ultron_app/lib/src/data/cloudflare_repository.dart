import 'dart:convert';

import 'package:http/http.dart' as http;

import '../domain/access.dart';
import '../domain/models.dart';
import 'repository.dart';

/// The live app API (services/app_api). Tokens live only in memory: relaunching the app asks to sign in.
class CloudflareRepository extends UltronRepository {
  CloudflareRepository({
    required Uri baseUrl,
    http.Client? client,
    this.onUnauthorized,
  }) : _base = baseUrl,
       _client = client ?? http.Client() {
    if ((baseUrl.scheme != 'https' &&
            !(baseUrl.scheme == 'http' &&
                ['127.0.0.1', 'localhost'].contains(baseUrl.host))) ||
        baseUrl.userInfo.isNotEmpty ||
        baseUrl.hasQuery ||
        baseUrl.hasFragment ||
        !['', '/'].contains(baseUrl.path)) {
      throw ArgumentError(
        'Use an HTTPS API origin, or loopback HTTP for local development.',
      );
    }
  }
  final Uri _base;
  final http.Client _client;
  final void Function()? onUnauthorized;
  String? _token;
  AppUser? _user;
  int _epoch = 0;
  @override
  AppUser? get currentUser => _user;
  void close() => _client.close();

  Future<({Map<String, dynamic> data, Map<String, String> headers})> _request(
    String method,
    String path, {
    Map<String, Object?>? body,
    bool authenticated = true,
  }) async {
    final epoch = _epoch;
    if (authenticated && _token == null) {
      throw const FrontendException('Sign in to continue.');
    }
    final request = http.Request(method, _base.resolve(path))
      ..followRedirects = false;
    request.headers['Accept'] = 'application/json';
    if (authenticated) request.headers['Authorization'] = 'Bearer $_token';
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    try {
      final response = await http.Response.fromStream(
        await _client.send(request).timeout(const Duration(seconds: 25)),
      ).timeout(const Duration(seconds: 25));
      if (epoch != _epoch) {
        throw const FrontendException('The session changed. Sign in again.');
      }
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, dynamic>) throw const FormatException();
      if (response.statusCode < 200 || response.statusCode >= 300) {
        if (response.statusCode == 401 && authenticated) {
          _token = null;
          _user = null;
          onUnauthorized?.call();
        }
        final message = decoded['error'] ?? decoded['message'];
        throw FrontendException(
          message is String
              ? message
              : 'The request was refused. Refresh and try again.',
        );
      }
      return (data: decoded, headers: response.headers);
    } on FrontendException {
      rethrow;
    } catch (_) {
      throw const FrontendException(
        'The service could not be reached. Check your connection and try again.',
      );
    }
  }

  @override
  Future<void> signIn(String username, String password) async {
    final epoch = _epoch;
    final response = await _request(
      'POST',
      '/api/auth/sign-in/username',
      body: {
        'username': username.trim(),
        'password': password,
        'rememberMe': false,
      },
      authenticated: false,
    );
    final token = response.headers['set-auth-token'] ?? response.data['token'];
    if (epoch != _epoch || token is! String || token.isEmpty) {
      throw const FrontendException('Sign-in could not finish.');
    }
    _token = token;
    try {
      await refreshUser();
    } catch (_) {
      _token = null;
      _user = null;
      rethrow;
    }
  }

  @override
  Future<void> register(String name, String username, String password) async {
    await _request(
      'POST',
      '/api/auth/sign-up/email',
      body: {
        'name': name.trim(),
        'username': username.trim(),
        'password': password,
      },
      authenticated: false,
    );
  }

  @override
  Future<void> signOut() async {
    final token = _token;
    ++_epoch;
    _token = null;
    _user = null;
    if (token != null) {
      try {
        final request = http.Request(
          'POST',
          _base.resolve('/api/auth/sign-out'),
        )..followRedirects = false;
        request.headers.addAll({
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        });
        request.body = '{}';
        await (await _client.send(request).timeout(const Duration(seconds: 10)))
            .stream
            .drain<void>()
            .timeout(const Duration(seconds: 10));
      } catch (_) {
        /* Local sign-out still completes when the service is offline. */
      }
    }
  }

  @override
  Future<AppUser> refreshUser() async {
    final response = await _request('GET', '/api/me');
    return _user = AppUser.fromJson(
      response.data['user'] as Map<String, dynamic>,
    );
  }

  @override
  Future<UserPage> listUsers({String search = '', int page = 0}) async {
    final query = Uri(queryParameters: {'search': search, 'page': '$page'})
        .query;
    final response = await _request('GET', '/api/admin/users?$query');
    return UserPage(
      (response.data['users'] as List)
          .map((u) => AppUser.fromJson(Map<String, dynamic>.from(u as Map)))
          .toList(),
      hasMore: response.data['hasMore'] == true,
    );
  }

  @override
  Future<List<AccessRole>> listRoles() async {
    final response = await _request('GET', '/api/admin/roles');
    return (response.data['roles'] as List)
        .map((r) => AccessRole.fromJson(Map<String, dynamic>.from(r as Map)))
        .toList();
  }

  @override
  Future<void> updateUser(
    AppUser user, {
    required String status,
    required String roleId,
  }) async {
    await _request(
      'PATCH',
      '/api/admin/users/${Uri.encodeComponent(user.id)}',
      body: {'status': status, 'roleId': roleId, 'revision': user.revision},
    );
  }

  @override
  Future<void> saveRole({
    required String id,
    required String name,
    required List<String> permissions,
    int? revision,
  }) async {
    await _request(
      'PUT',
      '/api/admin/roles/${Uri.encodeComponent(id)}',
      body: {'name': name, 'permissions': permissions, 'revision': revision},
    );
  }

  @override
  Future<AppUser> createUser({
    required String name,
    required String username,
    required String password,
    required String roleId,
    String email = '',
  }) async {
    final response = await _request(
      'POST',
      '/api/admin/users',
      body: {
        'name': name.trim(),
        'username': username.trim(),
        if (email.trim().isNotEmpty) 'email': email.trim(),
        'password': password,
        'roleId': roleId,
      },
    );
    return AppUser.fromJson(
      Map<String, dynamic>.from(response.data['user'] as Map),
    );
  }

  @override
  Future<AgentSettings> agentSettings() async {
    final response = await _request('GET', '/api/agent/settings');
    return AgentSettings.fromJson(
      Map<String, dynamic>.from(response.data['settings'] as Map),
    );
  }

  @override
  Future<AgentSettings> saveAgentSettings({
    required String model,
    required String tier,
    required List<String> order,
    required int revision,
  }) async {
    final response = await _request(
      'PUT',
      '/api/agent/settings',
      body: {
        'model': model.trim(),
        'tier': tier,
        'order': order,
        'revision': revision,
      },
    );
    return AgentSettings.fromJson(
      Map<String, dynamic>.from(response.data['settings'] as Map),
    );
  }

  @override
  Future<AgentMemory> agentMemory({
    String kind = '',
    String search = '',
  }) async {
    final query = Uri(queryParameters: {'kind': kind, 'search': search}).query;
    final response = await _request('GET', '/api/agent/memory?$query');
    return AgentMemory(
      (response.data['notes'] as List)
          .map((n) => AgentNote.fromJson(Map<String, dynamic>.from(n as Map)))
          .toList(),
      counts: Map<String, int>.from(
        (response.data['counts'] as Map? ?? const {}).map(
          (k, v) => MapEntry(k as String, (v as num).toInt()),
        ),
      ),
    );
  }

  @override
  Future<void> forgetNote(String id) async {
    await _request('DELETE', '/api/agent/memory/${Uri.encodeComponent(id)}');
  }

  List<SmsPhone> _phones(Map<String, dynamic> data) => (data['phones'] as List)
      .map((p) => SmsPhone.fromJson(Map<String, dynamic>.from(p as Map)))
      .toList();

  @override
  Future<List<SmsPhone>> smsPhones() async =>
      _phones((await _request('GET', '/api/admin/phones')).data);

  @override
  Future<List<SmsPhone>> blockPhone(
    SmsPhone phone, {
    required bool blocked,
  }) async => _phones(
    (await _request(
      'PATCH',
      '/api/admin/phones/${Uri.encodeComponent(phone.id)}',
      body: {'blocked': blocked, 'revision': phone.revision},
    )).data,
  );

  List<PhoneAgent> _agents(Map<String, dynamic> data) =>
      (data['agents'] as List)
          .map((a) => PhoneAgent.fromJson(Map<String, dynamic>.from(a as Map)))
          .toList();

  @override
  Future<List<PhoneAgent>> phoneAgents() async =>
      _agents((await _request('GET', '/api/admin/phone-agents')).data);

  @override
  Future<String> newPhoneAgent(String device) async {
    final response = await _request(
      'POST',
      '/api/admin/phone-agents',
      body: {'device': device},
    );
    return response.data['token'] as String;
  }

  @override
  Future<List<PhoneAgent>> revokePhoneAgent(String id) async => _agents(
    (await _request(
      'DELETE',
      '/api/admin/phone-agents/${Uri.encodeComponent(id)}',
    )).data,
  );
}
