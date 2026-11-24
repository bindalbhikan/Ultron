import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'dart:async';

import 'src/app.dart';
import 'src/data/app_updates.dart';
import 'src/data/sms_bridge.dart';
import 'src/state/providers.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  LicenseRegistry.addLicense(() async* {
    final license = await rootBundle.loadString('assets/fonts/OFL.txt');
    yield LicenseEntryWithLineBreaks(['DM Sans'], license);
  });
  // no one signed in and SMS only on: open its screen, not sign-in (it needs no account)
  final start = await const SmsBridge().isOn() ? '/sms' : '/login';
  final container = ProviderContainer(
    overrides: [startPathProvider.overrideWithValue(start)],
  );
  // a user signed in on an earlier run stays signed in: the kept session is read before the first screen
  await container
      .read(authProvider.notifier)
      .restore()
      .timeout(const Duration(seconds: 3), onTimeout: () {});
  unawaited(container.read(updatesProvider.notifier).check());
  runApp(
    UncontrolledProviderScope(container: container, child: const UltronApp()),
  );
}
