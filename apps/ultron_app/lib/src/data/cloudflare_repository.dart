import 'dart:convert';

import 'package:http/http.dart' as http;

import '../domain/access.dart';
import '../domain/models.dart';
import 'repository.dart';
import 'session_store.dart';

/// The live app API (services/app_api). The session is kept in [store] (the device's key store in the app),
/// so a signed-in user stays signed in after the app is closed, until they sign out or the session ends.
class CloudflareRepository extends UltronRepository {
  CloudflareRepository({
    required Uri baseUrl,
    http.Client? client,
    this.onUnauthorized,
    SessionStore? store,
  }) : _base = baseUrl,
       _client = client ?? http.Client(),
       _store = store ?? MemorySessionStore() {
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
  final SessionStore _store;
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
          _workspace = null;
          _token = null;
          _user = null;
          await _store.clear();
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
        'rememberMe': true,
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
      await _store.clear();
      rethrow;
    }
  }

  /// The session kept from an earlier run: its user at once (also offline). The caller checks it again
  /// with [refreshUser]; a 401 there clears it and asks to sign in.
  @override
  Future<AppUser?> restoreSession() async {
    final saved = await _store.read();
    if (saved == null) return null;
    try {
      _user = AppUser.fromJson(saved.user);
    } catch (_) {
      await _store.clear();
      return null;
    }
    _token = saved.token;
    return _user;
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
    _workspace = null;
    final token = _token;
    ++_epoch;
    _token = null;
    _user = null;
    await _store.clear();
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
    final json = response.data['user'] as Map<String, dynamic>;
    final user = _user = AppUser.fromJson(json);
    final token = _token;
    if (token != null) await _store.save(token, json);
    return user;
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

  @override
  Future<bool> setupNeeded() async {
    try {
      return (await _request(
            'GET',
            '/api/setup',
            authenticated: false,
          )).data['needed'] ==
          true;
    } on FrontendException {
      return false; // offline: sign-in shows its own error
    }
  }

  @override
  Future<void> firstAdmin({
    required String code,
    required String name,
    required String username,
    required String password,
  }) async {
    await _request(
      'POST',
      '/api/setup',
      body: {
        'code': code.trim(),
        'name': name.trim(),
        'username': username.trim(),
        'password': password,
      },
      authenticated: false,
    );
  }

  List<ApiKey> _keys(Map<String, dynamic> data) => (data['keys'] as List)
      .map((k) => ApiKey.fromJson(Map<String, dynamic>.from(k as Map)))
      .toList();

  @override
  Future<List<ApiKey>> apiKeys() async =>
      _keys((await _request('GET', '/api/agent/keys')).data);

  @override
  Future<List<ApiKey>> addApiKey({
    required String provider,
    required String key,
    String label = '',
  }) async => _keys(
    (await _request(
      'POST',
      '/api/agent/keys',
      body: {'provider': provider, 'key': key.trim(), 'label': label.trim()},
    )).data,
  );

  @override
  Future<List<ApiKey>> removeApiKey(String id) async => _keys(
    (await _request(
      'DELETE',
      '/api/agent/keys/${Uri.encodeComponent(id)}',
    )).data,
  );

  @override
  Future<List<ApiKey>> changeApiKey(
    String id, {
    String? move,
    bool reset = false,
  }) async => _keys(
    (await _request(
      'PATCH',
      '/api/agent/keys/${Uri.encodeComponent(id)}',
      body: {'move': ?move, if (reset) 'reset': true},
    )).data,
  );

  @override
  Future<Map<String, List<String>>> agentModels() =>
      _models('GET', '/api/agent/models');

  @override
  Future<Map<String, List<String>>> refreshModels() =>
      _models('POST', '/api/agent/models/refresh');

  Future<Map<String, List<String>>> _models(String method, String path) async {
    final data =
        (await _request(method, path)).data['models'] as Map? ?? const {};
    return data.map(
      (k, v) =>
          MapEntry(k as String, List<String>.from((v as Map)['ids'] as List)),
    );
  }

  // ---- the workspace, live from the worker through the app API (services/app_api /api/workspace)
  WorkspaceData? _workspace;

  static String _when(Object? iso) {
    final t = iso is String ? DateTime.tryParse(iso)?.toLocal() : null;
    if (t == null) return '-';
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 60) return '${d.inMinutes} min ago';
    if (d.inHours < 24) return '${d.inHours} h ago';
    return '${t.day.toString().padLeft(2, '0')}-${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][t.month - 1]} '
        '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
  }

  static RunStatus _status(Object? s) => switch (s) {
    'completed' => RunStatus.completed,
    'running' => RunStatus.running,
    'partial' => RunStatus.partial,
    'failed' => RunStatus.failed,
    _ => RunStatus.never,
  };

  @override
  Future<WorkspaceData> loadWorkspace() async {
    final d = (await _request('GET', '/api/workspace')).data;
    final chat = _user?.allows('agent.chat') == true
        ? (await _request('GET', '/api/agent/chat')).data
        : <String, dynamic>{};
    List<Map<String, dynamic>> list(String k) => (d[k] as List? ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    return _workspace = WorkspaceData(
      workflows: [
        for (final w in list('workflows'))
          Workflow(
            id: w['id'] as String,
            name: w['name'] as String,
            marketplace: w['marketplace'] as String? ?? 'All',
            schedule: w['auto'] == true
                ? 'Report · runs at once'
                : (w['action'] != null ? 'Needs approval' : 'Scheduled'),
            description: w['file'] as String? ?? '',
            status: _status(w['status']),
            updated: _when(w['updated']),
            action: w['action'] as String?,
            auto: w['auto'] == true,
            fields: Map<String, dynamic>.from(w['fields'] as Map? ?? const {}),
          ),
      ],
      runs: [
        for (final r in list('runs'))
          WorkflowRun(
            id: r['id'] as String,
            workflow: r['workflow'] as String,
            marketplace: r['marketplace'] as String? ?? 'All',
            status: _status(r['status']),
            started: _when(r['started']),
            duration: r['minutes'] == null ? 'running' : '${r['minutes']} min',
            note: r['note'] as String? ?? '',
            controllable: r['controllable'] == true,
          ),
      ],
      reports: [
        for (final r in list('reports'))
          ReportFile(
            id: r['id'] as String,
            name: r['name'] as String,
            period: _when(r['updated']),
            updated: _when(r['updated']),
            sources: [
              for (final n in (r['notes'] as List? ?? const []))
                SourceCoverage(n.toString(), available: true),
            ],
          ),
      ],
      approvals: [
        for (final a in list('approvals'))
          ApprovalRequest(
            id: a['id'] as String,
            title: (a['summary'] as String? ?? '').isEmpty
                ? '${a['action']}'
                : a['summary'] as String,
            additions: (a['inputs'] as Map? ?? const {}).length,
            destination: a['workflow'] as String? ?? '${a['action']}',
            expiresAt: a['expires'] == null
                ? DateTime.now().add(const Duration(hours: 24))
                : DateTime.fromMillisecondsSinceEpoch(
                    (a['expires'] as num).toInt(),
                  ),
          ),
      ],
      connections: [
        for (final c in list('connections'))
          PortalConnection(
            c['name'] as String,
            c['detail'] as String? ?? '',
            available: c['available'] == true,
          ),
      ],
      messages: [
        for (final message in (chat['messages'] as List? ?? const [])) ...[
          AgentMessage(text: message['question'] as String, fromOwner: true),
          AgentMessage(
            text: (message['answer'] as String? ?? '').isNotEmpty
                ? message['answer'] as String
                : 'Ultron is answering…',
            fromOwner: false,
            pending: ['queued', 'running'].contains(message['status']),
          ),
        ],
      ],
      schedule: [
        for (final s in list('schedule'))
          if (RegExp(r'^(\d{1,2}:\d{2} [AP]M)\s*(.*)$')
                  .firstMatch(s['ist'] as String? ?? '')
              case final m?)
            ScheduleItem(
              id: s['id'] as String? ?? '',
              cron: s['cron'] as String? ?? '',
              enabled: s['enabled'] != false,
              revision: (s['revision'] as num?)?.toInt() ?? 0,
              time: m.group(1)!,
              when: m.group(2)!,
              name: s['name'] as String? ?? '',
              portal: switch (s['portal']) {
                'myntra' => 'Myntra',
                'ajio' => 'AJIO',
                'flipkart' => 'Flipkart',
                _ => 'All',
              },
            ),
      ]..sort((a, b) => a.minutes.compareTo(b.minutes)),
    );
  }

  @override
  Future<WorkspaceData> requestRun(
    String workflowId, {
    required bool preview,
    Map<String, String> inputs = const {},
  }) async {
    final w = (_workspace ?? await loadWorkspace()).workflows
        .where((w) => w.id == workflowId)
        .firstOrNull;
    if (w?.action == null) {
      throw const FrontendException(
        'This working runs on its own schedule; it cannot be started from the app.',
      );
    }
    await _request(
      'POST',
      '/api/workflows/run',
      body: {'action': w!.action, 'inputs': inputs, 'preview': preview},
    );
    return preview ? (_workspace ?? await loadWorkspace()) : loadWorkspace();
  }

  @override
  Future<Map<String, dynamic>> control(
    String operation, {
    Map<String, Object?> args = const {},
    bool preview = false,
    bool confirmed = false,
  }) async => (await _request(
    'POST',
    '/api/agent/control',
    body: {
      'operation': operation,
      'args': args,
      'preview': preview,
      'confirmed': confirmed,
    },
  )).data;

  @override
  Future<WorkspaceData> decide(String id, ApprovalStatus decision) async {
    await _request(
      'POST',
      '/api/approvals/decide',
      body: {'id': id, 'approve': decision == ApprovalStatus.approved},
    );
    return loadWorkspace();
  }

  @override
  Future<WorkspaceData> sendMessage(String text) async {
    await _request('POST', '/api/agent/chat', body: {'text': text.trim()});
    return loadWorkspace();
  }
}
