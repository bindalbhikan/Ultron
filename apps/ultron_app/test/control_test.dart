import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ultron_app/src/data/cloudflare_repository.dart';
import 'package:ultron_app/src/domain/models.dart';

const _user = {
  'id': 'u1',
  'name': 'Owner',
  'email': 'owner@example.test',
  'status': 'active',
  'roleId': 'admin',
  'roleName': 'Administrator',
  'revision': 2,
  'emailVerified': false,
  'permissions': [
    'app.access',
    'users.manage',
    'agent.tools.read',
    'agent.manage',
    'memory.manage',
  ],
};

/// A signed-in CloudflareRepository whose server answers from `routes` ("METHOD /path" -> status, body).
Future<(CloudflareRepository, List<http.Request>)> signedIn(
  Map<String, (int, Object)> routes,
) async {
  final seen = <http.Request>[];
  final client = MockClient((request) async {
    seen.add(request);
    final key = '${request.method} ${request.url.path}';
    if (key == 'POST /api/auth/sign-in/username') {
      return http.Response(
        jsonEncode({'token': 't'}),
        200,
        headers: {'set-auth-token': 't'},
      );
    }
    if (key == 'GET /api/me') {
      return http.Response(jsonEncode({'user': _user}), 200);
    }
    final answer = routes[key];
    return answer == null
        ? http.Response('{"error":"Route unavailable."}', 404)
        : http.Response(jsonEncode(answer.$2), answer.$1);
  });
  final repository = CloudflareRepository(
    baseUrl: Uri.parse('https://api.example.test'),
    client: client,
  );
  await repository.signIn('owner', 'a-long-public-test-pass');
  return (repository, seen);
}

void main() {
  test(
    'Preview forwards parameters without treating it as a started run',
    () async {
      final (repository, seen) = await signedIn({
        'GET /api/workspace': (
          200,
          {
            'workflows': [
              {
                'id': 'inventory',
                'name': 'Inventory',
                'file': 'inventory.yml',
                'action': 'inventory',
                'status': 'none',
                'fields': {
                  'dry_run': {'description': 'Test only'},
                },
              },
            ],
          },
        ),
        'POST /api/workflows/run': (200, {'preview': true}),
        'POST /api/agent/control': (200, {'cancel': '123'}),
      });
      await repository.loadWorkspace();
      await repository.requestRun(
        'inventory',
        preview: true,
        inputs: {'dry_run': '1'},
      );
      expect(seen.last.url.path, '/api/workflows/run');
      expect(jsonDecode(seen.last.body), {
        'action': 'inventory',
        'inputs': {'dry_run': '1'},
        'preview': true,
      });
      expect(seen.where((r) => r.url.path == '/api/workspace').length, 1);
      await repository.control(
        'workflow.cancel',
        args: {'runId': '123'},
        confirmed: true,
      );
      expect(jsonDecode(seen.last.body), {
        'operation': 'workflow.cancel',
        'args': {'runId': '123'},
        'preview': false,
        'confirmed': true,
      });
    },
  );

  test('an administrator creates a user', () async {
    final (repository, seen) = await signedIn({
      'POST /api/admin/users': (
        201,
        {
          'user': {
            ..._user,
            'id': 'u2',
            'roleId': 'viewer',
            'roleName': 'Viewer',
          },
        },
      ),
    });
    final user = await repository.createUser(
      name: ' New ',
      username: ' newuser ',
      email: ' new@example.test ',
      password: 'a-long-public-test-pass',
      roleId: 'viewer',
    );
    expect(user.id, 'u2');
    final sent = jsonDecode(seen.last.body) as Map;
    expect(sent, {
      'name': 'New',
      'username': 'newuser',
      'email': 'new@example.test',
      'password': 'a-long-public-test-pass',
      'roleId': 'viewer',
    });
    expect(seen.last.headers['Authorization'], 'Bearer t');
  });

  test('model settings are read and saved with their revision; a refusal shows the server message', () async {
    final settings = {
      'model': 'auto',
      'tier': 'smart',
      'order': ['anthropic', 'cloudflare'],
      'revision': 3,
      'providers': [
        'anthropic',
        'openai',
        'google',
        'nvidia',
        'groq',
        'cloudflare',
      ],
      'tiers': ['smart', 'fast'],
    };
    final (repository, seen) = await signedIn({
      'GET /api/agent/settings': (200, {'settings': settings}),
      'PUT /api/agent/settings': (
        409,
        {'error': 'Settings changed. Refresh before saving.'},
      ),
    });
    final read = await repository.agentSettings();
    expect(read.auto, isTrue);
    expect(read.revision, 3);
    expect(read.providers.length, 6);
    await expectLater(
      repository.saveAgentSettings(
        model: 'groq:openai/gpt-oss-120b',
        tier: 'fast',
        order: ['groq'],
        revision: 3,
      ),
      throwsA(
        isA<FrontendException>().having(
          (e) => e.message,
          'message',
          contains('Refresh'),
        ),
      ),
    );
    expect(jsonDecode(seen.last.body), {
      'model': 'groq:openai/gpt-oss-120b',
      'tier': 'fast',
      'order': ['groq'],
      'revision': 3,
    });
  });

  test('memory is listed with counts and a note is forgotten', () async {
    final (repository, seen) = await signedIn({
      'GET /api/agent/memory': (
        200,
        {
          'notes': [
            {
              'id': 'a1b2c3',
              'kind': 'fact',
              'text': 'Ajio pays on Wednesdays',
              'tags': ['ajio'],
              'source': 'chat',
              'uses': 2,
              'created': 1,
              'updated': 1795360000,
            },
          ],
          'counts': {'fact': 1, 'incident': 4},
        },
      ),
      'DELETE /api/agent/memory/a1b2c3': (200, {'deleted': 'a1b2c3'}),
    });
    final memory = await repository.agentMemory(kind: 'fact', search: 'ajio');
    expect(seen.last.url.queryParameters, {'kind': 'fact', 'search': 'ajio'});
    expect(memory.notes.single.tags, ['ajio']);
    expect(memory.counts['incident'], 4);
    expect(memory.notes.single.updated.year, 2026);
    await repository.forgetNote('a1b2c3');
    expect(seen.last.method, 'DELETE');
  });
}
