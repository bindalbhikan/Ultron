import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:ultron_app/src/data/sms_bridge.dart';
import 'package:ultron_app/src/domain/access.dart';
import 'package:ultron_app/src/domain/models.dart';
import 'package:ultron_app/src/state/providers.dart';
import 'package:ultron_app/src/ui/sms_sheet_card.dart';

class _SignedIn extends AuthController {
  @override
  SessionState build() => const SessionState(
    user: AppUser(
      id: 'id-ramesh',
      name: 'Ramesh Kumar',
      email: 'ramesh@users.ultron.invalid',
      username: 'ramesh',
      status: 'active',
      roleId: 'team',
      roleName: 'Team',
      revision: 1,
      permissions: [],
    ),
  );
}

void main() {
  const channel = MethodChannel('ultron/sms');
  late List<MethodCall> calls;
  late Map<String, Object?> state;

  setUp(() {
    calls = [];
    state = {
      'on': false,
      'name': '',
      'sim': '',
      'phoneId': '0b7e3c1a-2f4d-4e5a-9b8c-1d2e3f4a5b6c',
      'sent': 0,
      'lastSent': 0,
      'log': '',
      'smsAllowed': false,
      'notificationsAllowed': true,
      'batteryFree': false,
      'maker': 'Xiaomi',
    };
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          switch (call.method) {
            case 'permissions':
              state['smsAllowed'] = true;
            case 'start':
              final args = call.arguments as Map;
              state.addAll({
                'on': true,
                'name': args['name'],
                'sim': args['sim'],
              });
            case 'stop':
              state['on'] = false;
            case 'battery':
              state['batteryFree'] = true;
          }
          return state;
        });
  });

  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null),
  );

  Future<void> open(WidgetTester tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [authProvider.overrideWith(_SignedIn.new)],
        child: const MaterialApp(
          home: Scaffold(body: SingleChildScrollView(child: SmsSheetCard())),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('the switch sends this phone\'s SMS as the signed-in user', (
    tester,
  ) async {
    await open(tester);
    await tester.tap(find.byKey(const Key('sms-sheet-switch')));
    await tester.pumpAndSettle();
    final start = calls.singleWhere((c) => c.method == 'start');
    expect(start.arguments, {
      'name': 'Ramesh Kumar',
      'sim': '',
      'worker': smsWorker,
    });
    expect(
      calls.map((c) => c.method),
      containsAllInOrder(['status', 'permissions', 'start', 'battery']),
    );
    expect(find.textContaining('As "Ramesh Kumar"'), findsOneWidget);
    expect(find.text('Battery: not restricted'), findsOneWidget);
  });

  testWidgets('already on under another name: renamed to the user', (
    tester,
  ) async {
    state.addAll({'on': true, 'name': 'Old Name', 'smsAllowed': true});
    await open(tester);
    final start = calls.singleWhere((c) => c.method == 'start');
    expect((start.arguments as Map)['name'], 'Ramesh Kumar');
  });

  testWidgets('switched off stops the forwarding', (tester) async {
    state.addAll({'on': true, 'name': 'Ramesh Kumar', 'smsAllowed': true});
    await open(tester);
    await tester.tap(find.byKey(const Key('sms-sheet-switch')));
    await tester.pumpAndSettle();
    expect(calls.last.method, 'stop');
    expect(state['on'], false);
  });
}
