import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../app_info.dart';
import '../data/app_updates.dart';

class UpdateNotice extends ConsumerWidget {
  const UpdateNotice({super.key, this.full = false});
  final bool full;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final update = ref.watch(updatesProvider);
    if (!full && update.release == null) return const SizedBox.shrink();
    final control = ref.read(updatesProvider.notifier);
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerLow,
      child: SafeArea(
        bottom: false,
        top: !full,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (full)
                Text(
                  'App updates · ${AppInfo.version}',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              if (update.message != null) Text(update.message!),
              const SizedBox(height: 8),
              Wrap(
                spacing: 12,
                runSpacing: 8,
                children: [
                  if (update.release != null)
                    FilledButton(
                      onPressed: update.busy ? null : control.install,
                      child: Text(
                        update.busy
                            ? 'Please wait…'
                            : 'Update to ${update.release!.version}',
                      ),
                    ),
                  if (full)
                    TextButton(
                      onPressed: update.busy ? null : control.check,
                      child: Text(
                        update.busy ? 'Checking…' : 'Check for updates',
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
