import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ultron_app/src/data/cloudflare_repository.dart';
import 'package:ultron_app/src/data/session_store.dart';

const _user = {
  'id': 'u1',
  'name': 'Owner',
  'email': 'owner@example.test',
  'status': 'active',
  'roleId': 'admin',
  'roleName': 'Administrator',
  'revision': 2,
  'emailVerified': false,
  'permissions': ['app.access'],
};

/// A server that signs in with token "t" and answers /api/me with [meStatus]; the sign-in bodies it saw.
(MockClient, List<Map<String, dynamic>>) _server({int meStatus = 200}) {
  final signIns = <Map<String, dynamic>>[];
  final client = MockClient((request) async {
    final key = '${request.method} ${request.url.path}';
    if (key == 'POST /api/auth/sign-in/username') {
      signIns.add(jsonDecode(request.body) as Map<String, dynamic>);
      return http.Response(
        jsonEncode({'token': 't'}),
        200,
        headers: {'set-auth-token': 't'},
      );
    }
    if (key == 'GET /api/me') {
      return meStatus == 200
          ? http.Response(jsonEncode({'user': _user}), 200)
          : http.Response('{"error":"Sign in to continue."}', meStatus);
    }
    if (key == 'POST /api/auth/sign-out') return http.Response('{}', 200);
    return http.Response('{"error":"Route unavailable."}', 404);
  });
  return (client, signIns);
}

CloudflareRepository _repo(http.Client client, SessionStore store) =>
    CloudflareRepository(
      baseUrl: Uri.parse('https://api.example.test'),
      client: client,
      store: store,
    );

void main() {
  test(
    'a sign-in is kept and the next start is signed in as that user',
    () async {
      final store = MemorySessionStore();
      final (client, signIns) = _server();
      await _repo(client, store).signIn('owner', 'a-long-public-test-pass');
      expect(signIns.single['rememberMe'], isTrue); // a long session, not 1 day
      expect(store.saved?.token, 't');

      final next = _repo(client, store); // the app opened again
      final user = await next.restoreSession();
      expect(user?.name, 'Owner');
      expect(next.currentUser?.id, 'u1');
      expect((await next.refreshUser()).name, 'Owner'); // the kept token works
    },
  );

  test('signing out forgets the kept session', () async {
    final store = MemorySessionStore();
    final (client, _) = _server();
    final repository = _repo(client, store);
    await repository.signIn('owner', 'a-long-public-test-pass');
    await repository.signOut();
    expect(store.saved, isNull);
    expect(await _repo(client, store).restoreSession(), isNull);
  });

  test('a session the server ended is forgotten and asks to sign in', () async {
    final store = MemorySessionStore()
      ..saved = (token: 'old', user: Map<String, dynamic>.of(_user));
    final (client, _) = _server(meStatus: 401);
    var asked = false;
    final repository = CloudflareRepository(
      baseUrl: Uri.parse('https://api.example.test'),
      client: client,
      store: store,
      onUnauthorized: () => asked = true,
    );
    expect(await repository.restoreSession(), isNotNull);
    await expectLater(repository.refreshUser(), throwsA(anything));
    expect(asked, isTrue);
    expect(store.saved, isNull);
  });

  test('nothing kept: no session', () async {
    final (client, _) = _server();
    expect(await _repo(client, MemorySessionStore()).restoreSession(), isNull);
  });
}
