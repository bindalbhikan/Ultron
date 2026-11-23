import 'package:flutter/services.dart';
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
  'agent.chat',
  'workflows.read',
  'workflows.run',
  'reports.read',
  'approvals.read',
  'approvals.decide',
  'analytics.read',
  'connections.read',
  'schedule.read',
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

  /// The live workspace, as the worker sends it through the app API.
  final started = <String>[];
  final decided = <String>[];
  var pending = true;
  WorkspaceData get _workspace => WorkspaceData(
    workflows: const [
      Workflow(
        id: 'sale',
        name: 'Daily sale report',
        marketplace: 'All',
        schedule: 'Report · runs at once',
        description: 'sale.yml',
        status: RunStatus.completed,
        updated: '5 min ago',
        action: 'sale',
        auto: true,
      ),
      Workflow(
        id: 'myntra-spf',
        name: 'Myntra SPF run',
        marketplace: 'Myntra',
        schedule: 'Needs approval',
        description: 'myntra-spf.yml',
        status: RunStatus.failed,
        updated: '2 h ago',
        action: 'myntraspf',
      ),
    ],
    runs: const [
      WorkflowRun(
        id: '1',
        workflow: 'Daily sale report',
        marketplace: 'All',
        status: RunStatus.completed,
        started: '5 min ago',
        duration: '2 min',
        note: 'success',
      ),
      WorkflowRun(
        id: '2',
        workflow: 'Myntra SPF run',
        marketplace: 'Myntra',
        status: RunStatus.failed,
        started: '2 h ago',
        duration: '12 min',
        note: 'failure',
      ),
    ],
    reports: const [
      ReportFile(
        id: 'sale',
        name: 'Sale report',
        period: '5 min ago',
        updated: '5 min ago',
        sources: [],
      ),
    ],
    approvals: [
      if (pending)
        ApprovalRequest(
          id: 'abc123def456',
          title: 'Run the Myntra SPF master for October',
          additions: 1,
          destination: 'myntra-spf.yml',
          expiresAt: DateTime(2030),
        ),
    ],
    connections: const [
      PortalConnection('Myntra MAIN', 'session saved today'),
      PortalConnection('Agent mode phone', 'Pixel · last seen now'),
    ],
    messages: const [],
    schedule: const [
      ScheduleItem(
        time: '9:30 AM',
        when: 'daily',
        name: 'Morning sale report',
        portal: 'All',
      ),
      ScheduleItem(
        time: '5:30 PM',
        when: 'daily',
        name: 'Myntra VMS',
        portal: 'Myntra',
      ),
    ],
  );
  @override
  Future<WorkspaceData> loadWorkspace() async => _workspace;
  @override
  Future<WorkspaceData> requestRun(
    String workflowId, {
    required bool preview,
  }) async {
    started.add(workflowId);
    return _workspace;
  }

  @override
  Future<WorkspaceData> decide(String id, ApprovalStatus decision) async {
    decided.add('$id:${decision.name}');
    pending = false;
    return _workspace;
  }

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
  bool setup = false;
  @override
  Future<bool> setupNeeded() async => setup;
  @override
  Future<void> firstAdmin({
    required String code,
    required String name,
    required String username,
    required String password,
  }) async {
    if (code != 'GOOD-CODE') {
      throw const FrontendException('The setup code is not right.');
    }
    accounts[username.toLowerCase()] = _user(username);
    setup = false;
  }

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
  final keys = <ApiKey>[
    ApiKey(
      id: 'k1',
      provider: 'groq',
      label: 'Free 1',
      last4: '1111',
      status: 'limit',
      restingUntil: DateTime.now().add(const Duration(hours: 1)),
    ),
    const ApiKey(
      id: 'k2',
      provider: 'groq',
      label: 'Free 2',
      last4: '2222',
      status: 'ok',
      restingUntil: null,
    ),
  ];
  @override
  Future<List<ApiKey>> apiKeys() async => keys;
  @override
  Future<List<ApiKey>> addApiKey({
    required String provider,
    required String key,
    String label = '',
  }) async {
    keys.add(
      ApiKey(
        id: 'k3',
        provider: provider,
        label: label,
        last4: key.substring(key.length - 4),
        status: 'ok',
        restingUntil: null,
      ),
    );
    return keys;
  }

  @override
  Future<Map<String, List<String>>> agentModels() async => models;
  var models = <String, List<String>>{
    'groq': ['openai/gpt-oss-120b'],
  };
  @override
  Future<Map<String, List<String>>> refreshModels() async => models = {
    ...models,
    'anthropic': [
      'claude-haiku-5-5',
      'claude-opus-5-5',
      'claude-sonnet-5-5',
      'claude-new-model',
    ],
  };
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
  bool setup = false,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final repo = FakeRepository(Map.of(_accounts))..setup = setup;
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
  testWidgets('with SMS only on, the app opens on SMS only, not sign-in', (
    tester,
  ) async {
    const sms = MethodChannel('ultron/sms');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          sms,
          (call) async => {
            'on': true,
            'name': 'Store phone',
            'smsAllowed': true,
          },
        );
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(sms, null),
    );
    final repo = FakeRepository(Map.of(_accounts));
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          repositoryProvider.overrideWithValue(repo),
          startPathProvider.overrideWithValue('/sms'),
        ],
        child: const UltronApp(),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('SMS only'), findsOneWidget);
    expect(find.textContaining('On: Store phone'), findsOneWidget);
    expect(find.byKey(const Key('auth-username')), findsNothing);
  });

  testWidgets(
    'first-time setup: the code makes the administrator, who lands signed in',
    (tester) async {
      await _open(tester, setup: true);
      await tester.tap(find.byKey(const Key('first-setup')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('setup-code')), 'WRONG-CODE');
      await tester.enterText(
        find.byKey(const Key('register-name')),
        'Owner Person',
      );
      await tester.enterText(find.byKey(const Key('auth-username')), 'Owner');
      await tester.enterText(
        find.byKey(const Key('auth-password')),
        'right-password',
      );
      await tester.enterText(
        find.byKey(const Key('register-confirm')),
        'right-password',
      );
      await tester.tap(find.byKey(const Key('auth-submit')));
      await tester.pumpAndSettle();
      expect(find.text('The setup code is not right.'), findsOneWidget);
      await tester.enterText(find.byKey(const Key('setup-code')), 'GOOD-CODE');
      await tester.tap(find.byKey(const Key('auth-submit')));
      await tester.pumpAndSettle();
      expect(find.textContaining('Hello, '), findsOneWidget);
    },
  );

  testWidgets('Brain shows each key with its state and adds a new one', (
    tester,
  ) async {
    final repo = await _open(tester, size: const Size(1280, 2400));
    await _signIn(tester, 'Bhikan');
    container(tester).read(routerProvider).go('/app/control');
    await tester.pumpAndSettle();
    expect(find.textContaining('••••1111'), findsOneWidget);
    expect(find.textContaining('Limit · back'), findsOneWidget);
    expect(find.text('Ready'), findsWidgets);
    await tester.tap(find.byKey(const Key('add-key')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('api-key-field')),
      'sk-test-abcdefghijklmnop9999',
    );
    await tester.tap(find.text('Add key').last);
    await tester.pumpAndSettle();
    expect(repo.keys.last.last4, '9999');
    expect(find.textContaining('••••9999'), findsOneWidget);
  });

  testWidgets('no setup button once an administrator exists', (tester) async {
    await _open(tester);
    expect(find.byKey(const Key('first-setup')), findsNothing);
  });

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
      expect(find.text('Hello, Bhikan Person'), findsOneWidget);
      expect(find.text('Daily sale report'), findsWidgets); // a live run
      expect(
        find.text('Run the Myntra SPF master for October'),
        findsOneWidget,
      );
      expect(
        find.text('Morning sale report'),
        findsOneWidget,
      ); // the worker's schedule
      for (final label in [
        'Home',
        'Agent',
        'Workflows',
        'Reports',
        'Approvals',
        'Analytics',
        'Connections',
        'Schedule',
        'Control panel',
        'Users',
        'Roles',
        'Profile & settings',
      ]) {
        expect(find.text(label), findsWidgets, reason: label);
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
    expect(find.text('Control panel'), findsNothing);
    expect(find.text('Workflows'), findsNothing);
    expect(find.text('Approvals'), findsNothing);
    expect(find.text('Home'), findsWidgets);
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
          '/app/agent',
          '/app/workflows',
          '/app/reports',
          '/app/approvals',
          '/app/analytics',
          '/app/connections',
          '/app/schedule',
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

  testWidgets('an approval decided in the app reaches the server', (
    tester,
  ) async {
    final repo = await _open(tester);
    await _signIn(tester, 'Bhikan');
    container(tester).read(routerProvider).go('/app/approvals');
    await tester.pumpAndSettle();
    expect(find.text('Run the Myntra SPF master for October'), findsWidgets);
    await tester.tap(find.text('Review changes').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Approve').last); // the confirm step
    await tester.pumpAndSettle();
    expect(repo.decided, ['abc123def456:approved']);
  });

  testWidgets('a refreshed model list is searched and picked', (tester) async {
    await _open(tester, size: const Size(1280, 2400));
    await _signIn(tester, 'Bhikan');
    container(tester).read(routerProvider).go('/app/control');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Auto-select the model'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('refresh-models')));
    await tester.pumpAndSettle();
    expect(find.text('4 models this provider offers'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('pick-model-anthropic')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('model-search')), 'new');
    await tester.pumpAndSettle();
    expect(find.text('1 of 4'), findsOneWidget);
    await tester.tap(find.text('claude-new-model'));
    await tester.pumpAndSettle();
    expect(find.text('claude-new-model'), findsOneWidget);
  });
}

ProviderContainer container(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(UltronApp)));
