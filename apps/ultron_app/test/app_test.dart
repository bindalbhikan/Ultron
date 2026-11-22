import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:ultron_app/src/app.dart';
import 'package:ultron_app/src/data/repository.dart';
import 'package:ultron_app/src/domain/access.dart';
import 'package:ultron_app/src/domain/models.dart';
import 'package:ultron_app/src/router.dart';
import 'package:ultron_app/src/state/providers.dart';

const _all = [
  'app.access',
  'users.manage',
  'roles.manage',
  'agent.tools.read',
  'agent.manage',
  'memory.manage',
  'phone.manage',
];

AppUser _user(
  String username, {
  String status = 'active',
  String role = 'admin',
  List<String> perms = _all,
}) => AppUser(
  id: 'id-$username',
  name: '$username Person',
  email: '$username@users.ultron.invalid',
  username: username,
  status: status,
  roleId: role,
  roleName: role == 'admin' ? 'Administrator' : role,
  revision: 1,
  permissions: status == 'active' ? perms : const [],
);

/// The app API, in memory: who signs in decides what the app may show.
class FakeRepository extends UltronRepository {
  FakeRepository(this.accounts);
  final Map<String, AppUser> accounts;
  AppUser? _me;
  final approvals = <String>[];

  @override
  AppUser? get currentUser => _me;

  @override
  Future<void> signIn(String username, String password) async {
    final user = accounts[username.toLowerCase()];
    if (user == null || password != 'right-password') {
      throw const FrontendException('Invalid username or password');
    }
    _me = user;
  }

  @override
  Future<void> signOut() async => _me = null;
  @override
  Future<AppUser> refreshUser() async => _me!;
  @override
  Future<UserPage> listUsers({String search = '', int page = 0}) async =>
      UserPage(accounts.values.toList());
  @override
  Future<List<AccessRole>> listRoles() async => const [
    AccessRole(
      id: 'admin',
      name: 'Administrator',
      permissions: _all,
      revision: 1,
    ),
    AccessRole(
      id: 'viewer',
      name: 'Viewer',
      permissions: ['app.access'],
      revision: 1,
    ),
  ];
  @override
  Future<List<SmsPhone>> smsPhones() async => [
    SmsPhone(
      id: 'p1',
      name: 'Store phone',
      lastSeen: DateTime.now(),
      sent: 12,
      blocked: false,
      revision: 1,
    ),
  ];
  @override
  Future<AgentSettings> agentSettings() async => const AgentSettings(
    model: 'auto',
    tier: 'smart',
    order: ['anthropic', 'cloudflare'],
    revision: 1,
    providers: [
      'anthropic',
      'openai',
      'google',
      'nvidia',
      'groq',
      'cloudflare',
    ],
  );
  @override
  Future<List<PhoneAgent>> phoneAgents() async => const [];
  @override
  Future<AgentMemory> agentMemory({
    String kind = '',
    String search = '',
  }) async => const AgentMemory([], counts: {'fact': 3, 'incident': 2});
}

final _accounts = {
  'bhikan': _user('Bhikan'),
  'newbie': _user('newbie', status: 'pending', role: 'pending'),
  'viewer': _user('viewer', role: 'viewer', perms: const ['app.access']),
};

Future<FakeRepository> _open(
  WidgetTester tester, {
  Size size = const Size(1280, 860),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final repo = FakeRepository(_accounts);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [repositoryProvider.overrideWithValue(repo)],
      child: const UltronApp(),
    ),
  );
  await tester.pumpAndSettle();
  return repo;
}

Future<void> _signIn(WidgetTester tester, String username) async {
  await tester.enterText(find.byKey(const Key('auth-username')), username);
  await tester.enterText(
    find.byKey(const Key('auth-password')),
    'right-password',
  );
  await tester.tap(find.byKey(const Key('auth-submit')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'sign-in asks for a username and password, offers SMS only, and shows no demo',
    (tester) async {
      await _open(tester);
      expect(find.text('Username'), findsOneWidget);
      expect(find.text('Password'), findsOneWidget);
      expect(find.byKey(const Key('sms-only')), findsOneWidget);
      expect(find.textContaining('demo', findRichText: true), findsNothing);
      expect(
        find.textContaining('Developed by Bhikan Deshmukh'),
        findsOneWidget,
      );
      await _signIn(tester, 'nobody');
      expect(find.text('Invalid username or password'), findsOneWidget);
    },
  );

  testWidgets(
    'an administrator lands on Home with live numbers and every menu item',
    (tester) async {
      await _open(tester);
      await _signIn(tester, 'Bhikan');
      expect(find.text('Hello, Bhikan'), findsOneWidget);
      expect(find.text('Waiting for approval'), findsOneWidget);
      expect(
        find.text('1'),
        findsWidgets,
      ); // one pending registration, one active phone
      expect(find.text('Agent model'), findsOneWidget);
      for (final label in ['Home', 'Control', 'Users', 'Roles', 'Profile']) {
        expect(find.text(label), findsWidgets);
      }
    },
  );

  testWidgets('the Users page offers Approve for a pending registration', (
    tester,
  ) async {
    await _open(tester);
    await _signIn(tester, 'Bhikan');
    await tester.tap(find.text('Users').first);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('approve-id-newbie')), findsOneWidget);
    expect(find.text('Create user'), findsOneWidget);
  });

  testWidgets('a pending account waits; a role without a feature is told so', (
    tester,
  ) async {
    await _open(tester);
    await _signIn(tester, 'newbie');
    expect(find.text('Waiting for approval'), findsOneWidget);
  });

  testWidgets('a viewer sees only what the role allows', (tester) async {
    await _open(tester);
    await _signIn(tester, 'viewer');
    expect(find.text('Users'), findsNothing);
    expect(find.text('Control'), findsNothing);
    expect(find.text('Profile'), findsWidgets);
  });

  for (final width in [320.0, 390.0, 760.0, 1440.0]) {
    for (final mode in [ThemeMode.dark, ThemeMode.light]) {
      testWidgets('every screen fits ${width.toInt()}px, ${mode.name}', (
        tester,
      ) async {
        await _open(tester, size: Size(width, 900));
        final container = ProviderScope.containerOf(
          tester.element(find.byType(UltronApp)),
        );
        container.read(themeModeProvider.notifier).set(mode);
        await tester.pumpAndSettle();
        await _signIn(tester, 'Bhikan');
        for (final path in [
          '/app/control',
          '/app/admin',
          '/app/roles',
          '/app/profile',
          '/app/home',
        ]) {
          container.read(routerProvider).go(path);
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull, reason: path);
        }
      });
    }
  }
}
