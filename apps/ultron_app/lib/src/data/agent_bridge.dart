import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'sms_bridge.dart' show smsWorker;

/// Agent mode on this phone, as the Android side reports it (MainActivity, kotlin/.../agent).
@immutable
class AgentStatus {
  const AgentStatus({
    required this.on,
    required this.device,
    required this.lastPoll,
    required this.lastJob,
    required this.log,
  });
  final bool on;
  final String device, lastJob, log;
  final DateTime? lastPoll;

  factory AgentStatus.fromMap(Map<Object?, Object?> m) {
    final poll = (m['lastPoll'] as num?)?.toInt() ?? 0;
    return AgentStatus(
      on: m['on'] == true,
      device: m['device'] as String? ?? 'This phone',
      lastPoll: poll > 0 ? DateTime.fromMillisecondsSinceEpoch(poll) : null,
      lastJob: m['lastJob'] as String? ?? '',
      log: m['log'] as String? ?? '',
    );
  }
}

/// Agent mode: the phone does work for the bots on its own line (Myntra style lookups of zero TD). The token
/// comes from the app API for this phone; it is never typed.
class AgentBridge {
  const AgentBridge();
  static const _channel = MethodChannel('ultron/agent');

  bool get supported =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  Future<AgentStatus> _call(
    String method, [
    Map<String, Object?>? args,
  ]) async => AgentStatus.fromMap(
    await _channel.invokeMapMethod<Object?, Object?>(method, args) ?? const {},
  );

  Future<AgentStatus> status() => _call('status');
  Future<AgentStatus> start(String token) =>
      _call('start', {'worker': smsWorker, 'token': token});
  Future<AgentStatus> stop() => _call('stop');
}
