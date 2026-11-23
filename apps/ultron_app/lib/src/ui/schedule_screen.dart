import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:material_ui/material_ui.dart';

import '../state/providers.dart';
import 'components.dart';

class ScheduleScreen extends ConsumerWidget {
  const ScheduleScreen({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final workspace = ref.watch(workspaceProvider);
    return PageBody(
      maxWidth: 900,
      children: [
        const PageHeading(
          'Schedule',
          subtitle: 'What the worker starts on its own · Asia/Kolkata',
        ),
        const NotePanel(
          'Live from the worker\'s cron schedule. Any working can also be started from Workflows.',
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
                        '${item.portal} · ${item.when}',
                        style: const TextStyle(fontSize: 12),
                      ),
                    ),
                    trailing: Text(
                      item.time,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
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
