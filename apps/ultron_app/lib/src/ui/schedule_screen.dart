import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:material_ui/material_ui.dart';

import '../domain/models.dart';
import '../state/providers.dart';
import 'components.dart';

class ScheduleScreen extends ConsumerStatefulWidget {
  const ScheduleScreen({super.key});
  @override
  ConsumerState<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends ConsumerState<ScheduleScreen> {
  bool _busy = false;

  String _time(String cron) {
    final parts = cron.split(' ');
    if (parts.length < 2) return cron;
    final minute = int.tryParse(parts[0]), hour = int.tryParse(parts[1]);
    if (minute == null || hour == null) return cron;
    final total = (hour * 60 + minute + 330) % 1440;
    final h = total ~/ 60;
    return '${h % 12 == 0 ? 12 : h % 12}:${(total % 60).toString().padLeft(2, '0')} ${h >= 12 ? 'PM' : 'AM'}';
  }

  Future<void> _edit(ScheduleItem item) async {
    setState(() => _busy = true);
    try {
      final repo = ref.read(repositoryProvider);
      final catalog = await repo.control('catalog');
      final times = (catalog['times'] as List? ?? []).cast<String>();
      if (!mounted) return;
      var enabled = item.enabled;
      var cron = item.cron;
      final saved = await showDialog<bool>(
        context: context,
        builder: (dialog) => StatefulBuilder(
          builder: (dialog, change) => AlertDialog(
            title: Text(item.name),
            content: SizedBox(
              width: 400,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Run automatically'),
                    value: enabled,
                    onChanged: (v) => change(() => enabled = v),
                  ),
                  DropdownButtonFormField<String>(
                    initialValue: cron,
                    isExpanded: true,
                    decoration: const InputDecoration(
                      labelText: 'Time · Asia/Kolkata',
                    ),
                    items: {cron, ...times}
                        .map(
                          (c) =>
                              DropdownMenuItem(value: c, child: Text(_time(c))),
                        )
                        .toList(),
                    onChanged: (v) {
                      if (v != null) change(() => cron = v);
                    },
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Applies to future triggers. ${item.when} stays the same.',
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialog, false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(dialog, true),
                child: const Text('Save schedule'),
              ),
            ],
          ),
        ),
      );
      if (saved != true) return;
      await repo.control(
        'schedule.set',
        args: {
          'id': item.id,
          'enabled': enabled,
          'cron': cron,
          'revision': item.revision,
        },
        confirmed: true,
      );
      await ref.read(workspaceProvider.notifier).refresh();
      if (mounted) {
        showNotice(context, 'Schedule saved for both app and Telegram.');
      }
    } on FrontendException catch (e) {
      if (mounted) showNotice(context, e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final workspace = ref.watch(workspaceProvider);
    final canManage =
        ref.watch(authProvider).user?.allows('agent.manage') == true;
    return PageBody(
      maxWidth: 900,
      children: [
        const PageHeading(
          'Schedule',
          subtitle: 'Shared agent schedule · Asia/Kolkata',
        ),
        const NotePanel(
          'Changes apply to future automatic starts. Pausing a task does not cancel an already running job.',
        ),
        const SizedBox(height: 22),
        ...workspace.when(
          loading: () => [const Center(child: CircularProgressIndicator())],
          error: (e, _) => [NotePanel('$e')],
          data: (data) => [
            if (data.schedule.isEmpty)
              const NotePanel('No scheduled workings were found.'),
            for (final item in data.schedule)
              Padding(
                padding: const EdgeInsets.only(bottom: 13),
                child: Card(
                  child: ListTile(
                    contentPadding: const EdgeInsets.all(16),
                    leading: PortalIcon(
                      item.portal,
                      icon: LucideIcons.calendarDays,
                    ),
                    title: Text(
                      item.name,
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    subtitle: Padding(
                      padding: const EdgeInsets.only(top: 5),
                      child: Text(
                        '${item.portal} · ${item.when}${item.enabled ? '' : ' · Paused'}',
                      ),
                    ),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          item.time,
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        if (canManage && item.id.isNotEmpty)
                          IconButton(
                            tooltip: 'Edit schedule',
                            onPressed: _busy ? null : () => _edit(item),
                            icon: const Icon(LucideIcons.pencil, size: 18),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }
}
