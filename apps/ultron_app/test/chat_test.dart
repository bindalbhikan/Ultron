import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ultron_app/src/data/cloudflare_repository.dart';
import 'package:ultron_app/src/data/session_store.dart';

void main() {
  test('chat submits privately, reloads pending replies and clears them on sign-out', () async {
    var answered = false;
    final sent = <String>[];
    final client = MockClient((request) async {
      final key = '${request.method} ${request.url.path}';
      if (key == 'GET /api/workspace') {
        return http.Response('{"workflows":[]}', 200);
      }
      if (key == 'POST /api/agent/chat') {
        sent.add((jsonDecode(request.body) as Map)['text'] as String);
        return http.Response('{"status":"queued"}', 202);
      }
      if (key == 'GET /api/agent/chat') {
        return http.Response(
          jsonEncode({
            'messages': [
              {
                'question': 'Hello',
                'answer': answered ? 'A private answer' : '',
                'status': answered ? 'completed' : 'queued',
              },
            ],
          }),
          200,
        );
      }
      return http.Response('{}', 200);
    });
    final repository = CloudflareRepository(
      baseUrl: Uri.parse('https://api.example.test'),
      client: client,
      store: MemorySessionStore()
        ..saved = (
          token: 'test-token',
          user: {
            'id': 'one',
            'name': 'One',
            'email': 'one@example.test',
            'status': 'active',
            'roleId': 'admin',
            'roleName': 'Administrator',
            'revision': 1,
            'emailVerified': false,
            'permissions': ['app.access', 'agent.chat'],
          },
        ),
    );
    await repository.restoreSession();
    final pending = await repository.sendMessage(' Hello ');
    expect(sent, ['Hello']);
    expect(pending.messages.first.text, 'Hello');
    expect(pending.messages.last.pending, isTrue);
    answered = true;
    final done = await repository.loadWorkspace();
    expect(done.messages.last.text, 'A private answer');
    expect(done.messages.last.pending, isFalse);
    await repository.signOut();
    await expectLater(repository.loadWorkspace(), throwsA(anything));
    repository.close();
  });

  test('an answer carries files: a picture loads with the session, a file opens by a one-use link', () async {
    final asked = <String>[];
    final client = MockClient((request) async {
      final key = '${request.method} ${request.url.path}';
      asked.add('$key ${request.headers['Authorization'] ?? ''}');
      if (key == 'GET /api/workspace') {
        return http.Response('{"workflows":[]}', 200);
      }
      if (key == 'GET /api/agent/chat') {
        return http.Response(
          jsonEncode({
            'messages': [
              {
                'question': 'ERP vs VMS image',
                'answer': 'Here it is',
                'status': 'completed',
                'files': [
                  {
                    'id': '00000000-0000-4000-8000-000000000003',
                    'name': 'NOV-26.png',
                    'mime': 'image/png',
                    'size': 3,
                    'caption': 'ERP vs VMS',
                  },
                ],
              },
            ],
          }),
          200,
        );
      }
      if (key ==
          'GET /api/agent/chat/files/00000000-0000-4000-8000-000000000003') {
        return http.Response.bytes([1, 2, 3], 200);
      }
      if (key ==
          'POST /api/agent/chat/files/00000000-0000-4000-8000-000000000003/link') {
        return http.Response(
          '{"url":"https://api.example.test/api/agent/chat/download/abc"}',
          200,
        );
      }
      return http.Response('{}', 404);
    });
    final repository = CloudflareRepository(
      baseUrl: Uri.parse('https://api.example.test'),
      client: client,
      store: MemorySessionStore()
        ..saved = (
          token: 'test-token',
          user: {
            'id': 'one',
            'name': 'One',
            'email': 'one@example.test',
            'status': 'active',
            'roleId': 'admin',
            'roleName': 'Administrator',
            'revision': 1,
            'emailVerified': false,
            'permissions': ['app.access', 'agent.chat'],
          },
        ),
    );
    await repository.restoreSession();
    final data = await repository.loadWorkspace();
    final file = data.messages.last.files.single;
    expect(file.name, 'NOV-26.png');
    expect(file.isImage, isTrue);
    expect(await repository.chatFileBytes(file.id), [1, 2, 3]);
    expect(
      (await repository.chatFileLink(file.id)).path,
      '/api/agent/chat/download/abc',
    );
    expect(
      asked,
      contains('GET /api/agent/chat/files/${file.id} Bearer test-token'),
    );
    repository.close();
  });
}
