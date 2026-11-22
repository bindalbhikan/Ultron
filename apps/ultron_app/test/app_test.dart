import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:ultron_app/src/app.dart';
import 'package:ultron_app/src/data/demo_repository.dart';
import 'package:ultron_app/src/domain/models.dart';
import 'package:ultron_app/src/router.dart';
import 'package:ultron_app/src/state/providers.dart';

Future<ProviderContainer> mountApp(
  WidgetTester tester, {
  bool signedIn = false,
  Size size = const Size(390, 844),
  double textScale = 1,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  final container = ProviderContainer(
    overrides: [
      repositoryProvider.overrideWithValue(
        DemoRepository(delay: Duration.zero),
      ),
    ],
  );
  addTearDown(container.dispose);
  if (signedIn) {
    await tester.runAsync(() async {
      await container
          .read(authProvider.notifier)
          .signIn(DemoRepository.demoEmail, DemoRepository.demoPassword);
      await container
          .read(authProvider.notifier)
          .verify(DemoRepository.demoCode);
    });
  }
  await tester.pumpWidget(
    UncontrolledProviderScope(container: container, child: const UltronApp()),
  );
  await tester.pumpAndSettle();
  return container;
}

Future<void> tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('login requires verification and includes developer credit', (
    tester,
  ) async {
    final container = await mountApp(tester);
    expect(find.text('Developed by Bhikan Deshmukh'), findsOneWidget);
    container.read(routerProvider).go('/app/reports');
    await tester.pumpAndSettle();
    expect(find.text('Welcome back'), findsOneWidget);
    await tapVisible(tester, find.byKey(const Key('fill-demo')));
    await tapVisible(tester, find.byKey(const Key('auth-submit')));
    expect(container.read(authProvider).phase, SessionPhase.verification);
    expect(find.text('Verify your sign-in'), findsOneWidget);
    await tester.enterText(
      find.byKey(const Key('verification-code')),
      '000000',
    );
    await tapVisible(tester, find.byKey(const Key('auth-submit')));
    expect(find.textContaining('Incorrect code'), findsOneWidget);
    await tester.enterText(
      find.byKey(const Key('verification-code')),
      DemoRepository.demoCode,
    );
    await tapVisible(tester, find.byKey(const Key('auth-submit')));
    expect(find.text("Today's operations"), findsOneWidget);
    expect(container.read(authProvider).phase, SessionPhase.signedIn);
    expect(tester.takeException(), isNull);
  });

  testWidgets('About credits developer and sign-out guards protected routes', (
    tester,
  ) async {
    final container = await mountApp(tester, signedIn: true);
    container.read(routerProvider).go('/app/profile');
    await tester.pumpAndSettle();
    await tapVisible(tester, find.text('About Ultron'));
    expect(find.text('Developed by Bhikan Deshmukh'), findsOneWidget);
    await tapVisible(tester, find.text('Close'));
    await tapVisible(tester, find.byKey(const Key('sign-out')));
    expect(find.text('Welcome back'), findsOneWidget);
    container.read(routerProvider).go('/app/phone');
    await tester.pumpAndSettle();
    expect(find.text('Welcome back'), findsOneWidget);
  });

  testWidgets('report detail names unavailable sources', (tester) async {
    final container = await mountApp(tester, signedIn: true);
    container.read(routerProvider).go('/app/reports');
    await tester.pumpAndSettle();
    await tapVisible(tester, find.text('Morning sale report'));
    expect(find.text('Excluded'), findsOneWidget);
    expect(find.textContaining('figures excluded'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'review, run request, chat and Phone Work controls stay within demo state',
    (tester) async {
      final container = await mountApp(tester, signedIn: true);
      container.read(routerProvider).go('/app/approvals');
      await tester.pumpAndSettle();
      await tapVisible(tester, find.text('Review changes'));
      await tapVisible(tester, find.text('Approve demo'));
      expect(
        container.read(workspaceProvider).requireValue.pendingApprovals,
        0,
      );

      container.read(routerProvider).go('/app/workflows');
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const Key('workflow-search')),
        'Inventory',
      );
      await tester.pumpAndSettle();
      expect(find.text('Morning sale report'), findsNothing);
      await tapVisible(tester, find.text('Inventory push'));
      await tapVisible(tester, find.text('Simulate request'));
      expect(
        container.read(workspaceProvider).requireValue.runs.first.duration,
        'Simulated',
      );

      container.read(routerProvider).go('/app/agent');
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 4));
      await tester.pumpAndSettle();
      final messageCount = container
          .read(workspaceProvider)
          .requireValue
          .messages
          .length;
      await tester.enterText(
        find.byKey(const Key('agent-message')),
        'Review the Myntra report',
      );
      await tapVisible(tester, find.byKey(const Key('agent-send')));
      expect(
        container.read(workspaceProvider).requireValue.messages.length,
        messageCount + 2,
      );
      expect(
        container
            .read(workspaceProvider)
            .requireValue
            .messages[messageCount]
            .text,
        'Review the Myntra report',
      );
      expect(
        container.read(workspaceProvider).requireValue.messages.last.sources,
        contains('Demo account health'),
      );

      container.read(routerProvider).go('/app/phone');
      await tester.pumpAndSettle();
      await tapVisible(tester, find.byKey(const Key('phone-agent-toggle')));
      expect(container.read(phonePreferencesProvider).agent, isTrue);
      expect(find.text('Not connected'), findsWidgets);
      expect(tester.takeException(), isNull);
    },
  );

  for (final width in [320.0, 390.0, 760.0, 1440.0]) {
    testWidgets('all screens fit a ${width.toInt()}px window', (tester) async {
      final container = await mountApp(
        tester,
        signedIn: true,
        size: Size(width, 1000),
      );
      for (final screen in [
        'home',
        'agent',
        'workflows',
        'reports',
        'approvals',
        'analytics',
        'profile',
        'phone',
        'connections',
        'schedule',
      ]) {
        container.read(routerProvider).go('/app/$screen');
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: '$screen at $width');
      }
    });
  }

  testWidgets('large text and dark theme keep core actions available', (
    tester,
  ) async {
    final container = await mountApp(
      tester,
      signedIn: true,
      size: const Size(390, 1000),
      textScale: 2,
    );
    container.read(themeModeProvider.notifier).set(ThemeMode.dark);
    for (final screen in [
      'home',
      'workflows',
      'reports',
      'approvals',
      'profile',
      'phone',
    ]) {
      container.read(routerProvider).go('/app/$screen');
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: '$screen at 200% text');
    }
  });
}
