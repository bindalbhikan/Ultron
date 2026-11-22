import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:material_ui/material_ui.dart';

import '../data/sms_bridge.dart';
import 'components.dart';

/// "SMS only": no account and no password. The person types a name once and chooses the SIM; from then
/// every SMS that phone receives goes to the SMS sheet with that name, also after a reboot.
class SmsOnlyScreen extends StatefulWidget {
  const SmsOnlyScreen({super.key, this.bridge = const SmsBridge()});
  final SmsBridge bridge;
  @override
  State<SmsOnlyScreen> createState() => _SmsOnlyScreenState();
}

class _SmsOnlyScreenState extends State<SmsOnlyScreen> {
  final _name = TextEditingController();
  SmsStatus? _status;
  String _sim = '';
  bool _busy = false;
  String? _error, _note;

  @override
  void initState() {
    super.initState();
    if (widget.bridge.supported) _refresh();
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
      _note = null;
    });
    try {
      await action();
    } on PlatformException catch (e) {
      if (mounted) setState(() => _error = e.message ?? 'That did not work.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _refresh() => _run(() async {
    final s = await widget.bridge.status();
    if (!mounted) return;
    setState(() {
      _status = s;
      if (_name.text.isEmpty) _name.text = s.name;
      _sim = s.sim;
    });
  });

  Future<void> _start() async {
    if (_name.text.trim().length < 2 || _name.text.trim().length > 40) {
      setState(() => _error = 'Type a name of 2 to 40 characters.');
      return;
    }
    await _run(() async {
      var s = await widget.bridge.askPermissions();
      if (!s.smsAllowed) {
        if (mounted) {
          setState(() {
            _status = s;
            _error = 'Allow SMS for ULTRON. Android 13+: if it is greyed out, App info → ⋮ → Allow restricted settings first.';
          });
        }
        return;
      }
      s = await widget.bridge.start(name: _name.text, sim: _sim);
      if (mounted) {
        setState(() {
          _status = s;
          _note = 'On. Every new SMS goes to the sheet as "${s.name}".';
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final s = _status;
    return Scaffold(
      appBar: AppBar(
        title: const Text('SMS only'),
        leading: IconButton(
          tooltip: 'Back to sign in',
          onPressed: () => context.go('/login'),
          icon: const Icon(LucideIcons.arrowLeft),
        ),
      ),
      body: PageBody(
        maxWidth: 560,
        children: [
          Text(
            'Send this phone\'s SMS to the SMS sheet',
            style: theme.textTheme.titleLarge,
          ),
          const SizedBox(height: 6),
          Text(
            'No account needed. Type your name once: it shows in the sheet next to every SMS from this phone. '
            'ULTRON keeps running in the background, also after a restart.',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 20),
          if (!widget.bridge.supported)
            const NotePanel(
              'SMS only works on an Android phone. Open ULTRON on the phone that receives the SMS.',
              warning: true,
            )
          else ...[
            TextField(
              key: const Key('sms-name'),
              controller: _name,
              enabled: !_busy && s?.on != true,
              maxLength: 40,
              decoration: const InputDecoration(
                labelText: 'Your name',
                hintText: 'e.g. Ramesh (store phone)',
              ),
            ),
            const SizedBox(height: 8),
            Text('Which SIM', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: '', label: Text('Both')),
                ButtonSegment(value: 'SIM 1', label: Text('SIM 1')),
                ButtonSegment(value: 'SIM 2', label: Text('SIM 2')),
              ],
              selected: {_sim},
              onSelectionChanged: _busy || s?.on == true
                  ? null
                  : (v) => setState(() => _sim = v.first),
            ),
            const SizedBox(height: 20),
            if (s?.on == true)
              OutlinedButton.icon(
                onPressed: _busy
                    ? null
                    : () => _run(() async {
                        final next = await widget.bridge.stop();
                        if (mounted) setState(() => _status = next);
                      }),
                icon: const Icon(LucideIcons.circleStop, size: 18),
                label: const Text('Turn SMS only off'),
              )
            else
              GradientButton(
                key: const Key('sms-start'),
                label: 'Start sending SMS',
                busy: _busy,
                onPressed: _start,
              ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              NotePanel(_error!, warning: true),
            ],
            if (_note != null) ...[
              const SizedBox(height: 12),
              NotePanel(_note!),
            ],
            if (s != null) ...[
              const SizedBox(height: 22),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _line(
                        s.on ? LucideIcons.circleCheck : LucideIcons.circle,
                        s.on
                            ? 'On: ${s.name} · ${s.sim.isEmpty ? 'both SIMs' : s.sim}'
                            : 'Off',
                      ),
                      _line(
                        LucideIcons.send,
                        '${s.sent} SMS sent${s.lastSent == null ? '' : ' · last ${s.lastSent!.toLocal().toString().substring(0, 16)}'}',
                      ),
                      _line(
                        s.smsAllowed
                            ? LucideIcons.messageSquare
                            : LucideIcons.triangleAlert,
                        s.smsAllowed ? 'SMS allowed' : 'SMS not allowed yet',
                      ),
                      if (!s.batteryFree)
                        TextButton.icon(
                          onPressed: _busy
                              ? null
                              : () => _run(() async {
                                  final next = await widget.bridge.askBattery();
                                  if (mounted) setState(() => _status = next);
                                }),
                          icon: const Icon(
                            LucideIcons.batteryWarning,
                            size: 18,
                          ),
                          label: const Text(
                            'Keep ULTRON awake (battery: don\'t optimise)',
                          ),
                        ),
                      if (s.on)
                        TextButton.icon(
                          onPressed: _busy
                              ? null
                              : () => _run(() async {
                                  final n = await widget.bridge.sendOld(60);
                                  if (mounted) {
                                    setState(
                                      () => _note =
                                          '$n SMS of the last 60 days queued. The sheet skips any it already has.',
                                    );
                                  }
                                }),
                          icon: const Icon(LucideIcons.history, size: 18),
                          label: const Text('Send old SMS (last 60 days)'),
                        ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: const Text('Activity'),
                children: [
                  SelectableText(
                    s.log.isEmpty ? 'Nothing yet.' : s.log,
                    style: theme.textTheme.bodySmall,
                  ),
                ],
              ),
              Align(
                alignment: Alignment.centerRight,
                child: IconButton(
                  tooltip: 'Refresh',
                  onPressed: _busy ? null : _refresh,
                  icon: const Icon(LucideIcons.refreshCw, size: 18),
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }

  Widget _line(IconData icon, String text) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      children: [
        Icon(icon, size: 18),
        const SizedBox(width: 10),
        Expanded(child: Text(text)),
      ],
    ),
  );
}
