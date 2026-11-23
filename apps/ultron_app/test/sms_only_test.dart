import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:ultron_app/src/data/sms_bridge.dart';
import 'package:ultron_app/src/ui/sms_only_screen.dart';

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
      'batteryFree': true,
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
          }
          return state;
        });
  });

  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null),
  );

  Future<void> open(WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: SmsOnlyScreen()));
    await tester.pumpAndSettle();
  }

  testWidgets('a name and a SIM turn SMS only on, through the worker', (
    tester,
  ) async {
    await open(tester);
    await tester.enterText(find.byKey(const Key('sms-name')), ' Ramesh ');
    await tester.tap(find.text('SIM 2'));
    await tester.tap(find.byKey(const Key('sms-start')));
    await tester.pumpAndSettle();
    final start = calls.singleWhere((c) => c.method == 'start');
    expect(start.arguments, {
      'name': 'Ramesh',
      'sim': 'SIM 2',
      'worker': smsWorker,
    });
    expect(
      calls.map((c) => c.method),
      containsAllInOrder(['status', 'permissions', 'start']),
    );
    expect(find.textContaining('On: Ramesh · SIM 2'), findsOneWidget);
    expect(find.text('Turn SMS only off'), findsOneWidget);
  });

  testWidgets('a short name is refused before anything is asked', (
    tester,
  ) async {
    await open(tester);
    await tester.enterText(find.byKey(const Key('sms-name')), 'R');
    await tester.tap(find.byKey(const Key('sms-start')));
    await tester.pumpAndSettle();
    expect(find.textContaining('2 to 40 characters'), findsOneWidget);
    expect(calls.map((c) => c.method), ['status']);
  });

  testWidgets('without the SMS permission it explains instead of starting', (
    tester,
  ) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          return state; // the person declined: smsAllowed stays false
        });
    await open(tester);
    await tester.enterText(find.byKey(const Key('sms-name')), 'Ramesh');
    await tester.tap(find.byKey(const Key('sms-start')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Allow SMS for ULTRON'), findsOneWidget);
    expect(calls.any((c) => c.method == 'start'), isFalse);
  });

  testWidgets(
    'Agent mode on this phone shows its line, with the last check-in',
    (tester) async {
      const agent = MethodChannel('ultron/agent');
      final poll = DateTime(2026, 11, 23, 10, 45);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            agent,
            (call) async => {
              'on': true,
              'device': 'Xiaomi 13',
              'lastPoll': poll.millisecondsSinceEpoch,
              'lastJob': '',
              'log': '',
            },
          );
      addTearDown(
        () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(agent, null),
      );
      await open(tester);
      expect(
        find.text('Agent mode (Myntra) on · last check-in 2026-11-23 10:45'),
        findsOneWidget,
      );
    },
  );

  testWidgets('without Agent mode in the app the line is left out', (
    tester,
  ) async {
    await open(tester); // ultron/agent not answered: MissingPluginException
    expect(find.textContaining('Agent mode'), findsNothing);
    expect(find.text('Start sending SMS'), findsOneWidget);
  });
}
