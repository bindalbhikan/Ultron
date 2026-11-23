import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// The worker that takes the SMS of "SMS only" phones (POST /api/sms). It holds the sheet's link and key,
/// so a phone needs no setup; a seller's own build passes its worker with --dart-define=ULTRON_WORKER=...
const smsWorker = String.fromEnvironment(
  'ULTRON_WORKER',
  defaultValue: 'https://bindal-telegram-bot.bhikan-serein.workers.dev',
);

/// "SMS only" mode, as the Android side reports it (MainActivity, kotlin/.../sms).
@immutable
class SmsStatus {
  const SmsStatus({
    required this.on,
    required this.name,
    required this.sim,
    required this.phoneId,
    required this.sent,
    required this.lastSent,
    required this.log,
    required this.smsAllowed,
    required this.notificationsAllowed,
    required this.batteryFree,
  });

  final bool on, smsAllowed, notificationsAllowed, batteryFree;
  final String name, sim, phoneId, log;
  final int sent;
  final DateTime? lastSent;

  factory SmsStatus.fromMap(Map<Object?, Object?> m) {
    final last = (m['lastSent'] as num?)?.toInt() ?? 0;
    return SmsStatus(
      on: m['on'] == true,
      name: m['name'] as String? ?? '',
      sim: m['sim'] as String? ?? '',
      phoneId: m['phoneId'] as String? ?? '',
      sent: (m['sent'] as num?)?.toInt() ?? 0,
      lastSent: last > 0 ? DateTime.fromMillisecondsSinceEpoch(last) : null,
      log: m['log'] as String? ?? '',
      smsAllowed: m['smsAllowed'] == true,
      notificationsAllowed: m['notificationsAllowed'] == true,
      batteryFree: m['batteryFree'] == true,
    );
  }
}

/// The Android side of "SMS only" mode. Only Android phones receive SMS; elsewhere [supported] is false.
class SmsBridge {
  const SmsBridge();

  static const _channel = MethodChannel('ultron/sms');

  bool get supported =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  Future<SmsStatus> _call(String method, [Map<String, Object?>? args]) async {
    final result = await _channel.invokeMapMethod<Object?, Object?>(
      method,
      args,
    );
    return SmsStatus.fromMap(result ?? const {});
  }

  Future<SmsStatus> status() => _call('status');

  /// Whether SMS only is on, for the first screen: false off Android or when Android does not answer in time.
  Future<bool> isOn() async {
    if (!supported) return false;
    try {
      return (await status().timeout(const Duration(seconds: 2))).on;
    } catch (_) {
      return false;
    }
  }

  /// Asks for the SMS (and, Android 13+, notification) permissions; the status after the answer.
  Future<SmsStatus> askPermissions() => _call('permissions');

  /// Opens Android's "don't optimise battery" prompt for ULTRON.
  Future<SmsStatus> askBattery() => _call('battery');

  /// Turns SMS only on: every new SMS (of [sim]: '' both, 'SIM 1', 'SIM 2') goes to the sheet as [name].
  Future<SmsStatus> start({required String name, required String sim}) =>
      _call('start', {'name': name.trim(), 'sim': sim, 'worker': smsWorker});

  Future<SmsStatus> stop() => _call('stop');

  /// Queues the inbox of the last [days] days; the sheet skips SMS it already has. The count queued.
  Future<int> sendOld(int days) async =>
      await _channel.invokeMethod<int>('sendOld', {'days': days}) ?? 0;
}
