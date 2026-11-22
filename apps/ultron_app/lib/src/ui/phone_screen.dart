import 'package:flutter/foundation.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../state/providers.dart';
import 'actions.dart';
import 'components.dart';

class PhoneScreen extends ConsumerStatefulWidget {
  const PhoneScreen({super.key});
  @override
  ConsumerState<PhoneScreen> createState() => _PhoneScreenState();
}

class _PhoneScreenState extends ConsumerState<PhoneScreen> {
  final _senders = TextEditingController();
  @override
  void dispose() {
    _senders.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final settings = ref.watch(phonePreferencesProvider);
    final nativeAndroid =
        !kIsWeb && defaultTargetPlatform == TargetPlatform.android;
    final notifier = ref.read(phonePreferencesProvider.notifier);
    return PageBody(
      maxWidth: 1000,
      children: [
        const PageHeading(
          'Phone Work',
          subtitle: 'Agent mode, SMS, courier OTPs and POD handling.',
        ),
        EmeraldPanel(
          child: Row(
            children: [
              const Icon(LucideIcons.smartphone, size: 39),
              const SizedBox(width: 18),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Your phone, part of Ultron',
                      style: TextStyle(
                        fontSize: 21,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 7),
                    Text(
                      nativeAndroid
                          ? 'Android service connection pending'
                          : 'Manage here · On-device work runs on Android',
                      style: const TextStyle(
                        fontSize: 12,
                        color: Color(0xFFD8F4E5),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 22),
        const NotePanel(
          'Frontend setup only. The old Phone app still owns the active services until migration is completed and tested.',
          warning: true,
        ),
        const SectionHeading('Agent mode'),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              children: [
                SwitchListTile.adaptive(
                  key: const Key('phone-agent-toggle'),
                  contentPadding: EdgeInsets.zero,
                  title: const Text(
                    'Agent mode · Demo control',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                  ),
                  subtitle: const Text(
                    'Myntra lookup jobs when a PC cannot serve them.',
                    style: TextStyle(fontSize: 12),
                  ),
                  value: settings.agent,
                  onChanged: (value) =>
                      notifier.update(settings.copyWith(agent: value)),
                ),
                const DetailRow('Service', 'Not connected'),
                const DetailRow('Last check-in', 'Unavailable'),
                const DetailRow('Last job', 'Unavailable'),
                OutlinedButton.icon(
                  onPressed: () => _runtimeInfo(context),
                  icon: const Icon(LucideIcons.refreshCw, size: 17),
                  label: const Text('Check device connection'),
                ),
              ],
            ),
          ),
        ),
        const SectionHeading('SMS to sheet'),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  title: const Text(
                    'SMS sync · Demo control',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                  ),
                  subtitle: const Text(
                    'Receive, queue, retry and deduplicate incoming SMS.',
                    style: TextStyle(fontSize: 12),
                  ),
                  value: settings.sms,
                  onChanged: (value) =>
                      notifier.update(settings.copyWith(sms: value)),
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<String>(
                  isExpanded: true,
                  initialValue: settings.sim,
                  decoration: const InputDecoration(labelText: 'SIM selection'),
                  items: ['Both SIMs', 'SIM 1', 'SIM 2']
                      .map(
                        (sim) => DropdownMenuItem(
                          value: sim,
                          child: Text(
                            sim,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      )
                      .toList(),
                  onChanged: (value) {
                    if (value != null) {
                      notifier.update(settings.copyWith(sim: value));
                    }
                  },
                ),
                const SizedBox(height: 18),
                TextField(
                  controller: _senders,
                  decoration: const InputDecoration(
                    labelText: 'Sender filter',
                    hintText: 'Optional sender names',
                  ),
                  onChanged: (value) => notifier.update(
                    ref.read(phonePreferencesProvider).copyWith(senders: value),
                  ),
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    OutlinedButton.icon(
                      onPressed: () => _runtimeInfo(context),
                      icon: const Icon(LucideIcons.shieldCheck, size: 16),
                      label: const Text('SMS permission'),
                    ),
                    OutlinedButton.icon(
                      onPressed: () => _runtimeInfo(context),
                      icon: const Icon(LucideIcons.send, size: 16),
                      label: const Text('Send test row'),
                    ),
                    OutlinedButton.icon(
                      onPressed: () => _runtimeInfo(context),
                      icon: const Icon(LucideIcons.history, size: 16),
                      label: const Text('Import last 60 days'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SectionHeading('Courier OTP & POD'),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(
                  children: [
                    PortalIcon('All', icon: LucideIcons.fileCheck2),
                    SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Capture OTPs and receipt evidence',
                        style: TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 15),
                const Text(
                  'Delhivery, Shadowfax, Ekart and XpressBees messages are part of the migration. Download time-limited POD links, read AWBs, update the daily OTP sheet, and retain receipt evidence.',
                ),
                const SizedBox(height: 16),
                const DetailRow('OTP sync', 'Not connected'),
                const DetailRow('POD queue', 'Unavailable'),
                const DetailRow('Duplicates', 'Unavailable'),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: () => _runtimeInfo(context),
                  icon: const Icon(LucideIcons.listChecks, size: 17),
                  label: const Text('View processing log'),
                ),
              ],
            ),
          ),
        ),
        const SectionHeading('Device setup'),
        Card(
          child: Column(
            children: [
              ListTile(
                leading: const Icon(LucideIcons.batteryCharging),
                title: const Text(
                  'Battery & background access',
                  style: TextStyle(fontSize: 13),
                ),
                subtitle: const Text(
                  'Foreground notification, battery settings and autostart.',
                  style: TextStyle(fontSize: 11),
                ),
                trailing: const Icon(LucideIcons.chevronRight, size: 16),
                onTap: () => _runtimeInfo(context),
              ),
              ListTile(
                leading: const Icon(LucideIcons.rotateCcw),
                title: const Text(
                  'Restart after reboot',
                  style: TextStyle(fontSize: 13),
                ),
                subtitle: const Text(
                  'Resume authorised on-device work after a restart.',
                  style: TextStyle(fontSize: 11),
                ),
                trailing: const Icon(LucideIcons.chevronRight, size: 16),
                onTap: () => _runtimeInfo(context),
              ),
            ],
          ),
        ),
      ],
    );
  }

  void _runtimeInfo(BuildContext context) => showDetail(
    context,
    'Android runtime connection',
    const Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'The frontend is ready to present these controls, but the Android services have not yet been migrated. No SMS permission is requested, no SMS is read, and no background job is started by these demo controls.',
        ),
        SizedBox(height: 16),
        Text(
          'The migration must preserve the existing job protocol, SIM/sender filters, deduplication, retry queues, OTP/POD rules and reboot behaviour before replacing the old app.',
        ),
      ],
    ),
  );
}
