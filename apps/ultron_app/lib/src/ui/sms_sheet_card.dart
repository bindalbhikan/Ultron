import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:material_ui/material_ui.dart';

import '../data/sms_bridge.dart';
import '../state/providers.dart';
import 'components.dart';

/// "SMS to OTP sheet" for a signed-in person (owner, 25 Nov 2026): the same Android forwarding as SMS only
/// (sms/SmsReceiver -> SmsUpload -> the worker -> the sheet), named after the signed-in user, switched on and off
/// here because a signed-in person never sees the SMS only screen. Shows whether it is really running (SMS
/// allowed, battery exemption, the last SMS sent) and opens the phone's battery and auto-start pages, which
/// Xiaomi / Oppo / Vivo / Realme phones need or they stop the app in the background. Android only.
class SmsSheetCard extends ConsumerStatefulWidget {
  const SmsSheetCard({super.key, this.bridge = const SmsBridge()});
  final SmsBridge bridge;

  @override
  ConsumerState<SmsSheetCard> createState() => _SmsSheetCardState();
}

class _SmsSheetCardState extends ConsumerState<SmsSheetCard>
    with WidgetsBindingObserver {
  SmsStatus? _status;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    if (widget.bridge.supported) _refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  // back from Android's battery / auto-start page: show what changed
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && widget.bridge.supported) {
      _refresh();
    }
  }

  static const _sheetAliases = {
    'bhikan': 'Bhikan',
    'vipul': 'Vipul',
    'asif': 'Asif',
    'rahul': 'RAHUL',
  };

  /// The sheet's name for this phone: the signed-in user's name (matched to the OTP sheet's Name
  /// dropdown when known, e.g. "bhikan deshmukh" -> "Bhikan"), else the username.
  String get _sheetName {
    final user = ref.read(authProvider).user;
    final name = (user?.name ?? '').replaceAll(RegExp(r'\s+'), ' ').trim();
    if (name.length >= 2) {
      final first = name.split(' ').first.toLowerCase();
      final mapped = _sheetAliases[first];
      if (mapped != null) return mapped;
      return name.length > 40 ? name.substring(0, 40) : name;
    }
    return (user?.username ?? 'ULTRON user').padRight(2, '_');
  }

  Future<void> _run(Future<SmsStatus?> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final s = await action();
      if (mounted && s != null) setState(() => _status = s);
    } on PlatformException catch (e) {
      if (mounted) setState(() => _error = e.message ?? 'That did not work.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _refresh() => _run(() async {
    final s = await widget.bridge.status();
    // on, but under an old name (SMS only before signing in, or the name changed): the user's name now
    if (s.on && s.name != _sheetName) {
      return widget.bridge.start(name: _sheetName, sim: s.sim);
    }
    return s;
  });

  Future<void> _turn(bool on, {String? sim}) => _run(() async {
    if (!on) return widget.bridge.stop();
    var s = await widget.bridge.askPermissions();
    if (!s.smsAllowed) {
      _error = 'Allow SMS for ULTRON. Android 13+: if it is greyed out, App info → ⋮ → Allow restricted settings first.';
      return s;
    }
    s = await widget.bridge.start(
      name: _sheetName,
      sim: sim ?? _status?.sim ?? '',
    );
    // the exemption keeps it running when the phone sleeps; asked once, the person can say no
    if (!s.batteryFree) s = await widget.bridge.askBattery();
    return s;
  });

  @override
  Widget build(BuildContext context) {
    if (!widget.bridge.supported) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final s = _status;
    final on = s?.on ?? false;
    final last = s?.lastSent;
    final ready = on && (s?.smsAllowed ?? false) && (s?.batteryFree ?? false);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SectionHeading('SMS to OTP sheet'),
        Card(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SwitchListTile(
                  key: const Key('sms-sheet-switch'),
                  contentPadding: EdgeInsets.zero,
                  value: on,
                  onChanged: _busy || s == null ? null : (v) => _turn(v),
                  title: const Text('Send this phone\'s SMS to the OTP sheet'),
                  subtitle: Text(
                    on
                        ? 'As "${s!.name}" · ${s.sim.isEmpty ? 'both SIMs' : s.sim}'
                        : 'Every new SMS of this phone goes to the sheet with your name, also when the app is closed.',
                  ),
                ),
                if (on) ...[
                  const SizedBox(height: 4),
                  SegmentedButton<String>(
                    segments: const [
                      ButtonSegment(value: '', label: Text('Both SIMs')),
                      ButtonSegment(value: 'SIM 1', label: Text('SIM 1')),
                      ButtonSegment(value: 'SIM 2', label: Text('SIM 2')),
                    ],
                    selected: {s!.sim},
                    onSelectionChanged: _busy
                        ? null
                        : (v) => _turn(true, sim: v.first),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      StatusPill(
                        s.smsAllowed ? 'SMS allowed' : 'SMS not allowed',
                        tone: s.smsAllowed ? Tone.good : Tone.bad,
                      ),
                      StatusPill(
                        s.batteryFree
                            ? 'Battery: not restricted'
                            : 'Battery: restricted',
                        tone: s.batteryFree ? Tone.good : Tone.warn,
                      ),
                      StatusPill('${s.sent} sent'),
                      if (last != null)
                        StatusPill(
                          'Last ${last.toLocal().toString().substring(0, 16)}',
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    ready
                        ? 'Running. It uses battery only when an SMS arrives (one short send each).'
                        : 'To keep it running when the phone sleeps: allow the battery exemption and, on '
                              '${s.maker.isEmpty ? 'this phone' : s.maker}, turn on auto-start for ULTRON.',
                    style: theme.textTheme.bodySmall,
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      if (!s.batteryFree)
                        OutlinedButton.icon(
                          onPressed: _busy
                              ? null
                              : () => _run(widget.bridge.askBattery),
                          icon: const Icon(
                            LucideIcons.batteryCharging,
                            size: 18,
                          ),
                          label: const Text('Battery exemption'),
                        ),
                      OutlinedButton.icon(
                        onPressed: _busy
                            ? null
                            : () => _run(widget.bridge.openAutostart),
                        icon: const Icon(LucideIcons.rocket, size: 18),
                        label: const Text('Auto-start setting'),
                      ),
                    ],
                  ),
                  if (s.log.isNotEmpty)
                    ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: const Text('Recent activity'),
                      children: [
                        SelectableText(
                          s.log.split('\n').take(20).join('\n'),
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontFamily: 'monospace',
                          ),
                        ),
                      ],
                    ),
                ],
                if (_error != null) ...[
                  const SizedBox(height: 8),
                  NotePanel(_error!, warning: true),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}
