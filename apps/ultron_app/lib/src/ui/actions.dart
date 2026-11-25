import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../domain/models.dart';
import '../state/providers.dart';
import 'components.dart';

Future<void> showRunWorkflow(BuildContext context, {Workflow? workflow}) =>
    showDialog<void>(
      context: context,
      builder: (_) => _RunDialog(initial: workflow),
    );

class _RunDialog extends ConsumerStatefulWidget {
  const _RunDialog({this.initial});
  final Workflow? initial;
  @override
  ConsumerState<_RunDialog> createState() => _RunDialogState();
}

class _RunDialogState extends ConsumerState<_RunDialog> {
  String? _workflow;
  final Map<String, TextEditingController> _inputs = {};

  @override
  void dispose() {
    for (final input in _inputs.values) {
      input.dispose();
    }
    super.dispose();
  }

  bool _preview = true;
  bool _busy = false;
  String? _error;

  Future<void> _submit(String id) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(workspaceProvider.notifier)
          .requestRun(
            id,
            preview: _preview,
            inputs: {
              for (final entry in _inputs.entries)
                if (entry.value.text.trim().isNotEmpty)
                  entry.key: entry.value.text.trim(),
            },
          );
      if (!mounted) return;
      showNotice(
        context,
        _preview
            ? 'Preview validated. Nothing was started or changed.'
            : 'Started. Follow its progress in Workflows.',
      );
      Navigator.pop(context);
    } on FrontendException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'The request could not finish. Try again.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final workflows =
        ref.watch(workspaceProvider).asData?.value.workflows ??
        const <Workflow>[];
    final selected =
        _workflow ?? widget.initial?.id ?? workflows.firstOrNull?.id;
    final workflow = workflows.where((item) => item.id == selected).firstOrNull;
    return AlertDialog(
      title: const Text('Run workflow'),
      content: SizedBox(
        width: 430,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Review the working and its execution scope.'),
              const SizedBox(height: 20),
              DropdownButtonFormField<String>(
                initialValue: selected,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Workflow'),
                items: workflows
                    .map(
                      (item) => DropdownMenuItem(
                        value: item.id,
                        child: Text(item.name, overflow: TextOverflow.ellipsis),
                      ),
                    )
                    .toList(),
                onChanged: _busy
                    ? null
                    : (value) => setState(() {
                        _workflow = value;
                        for (final controller in _inputs.values) {
                          controller.clear();
                        }
                      }),
              ),
              if (workflow != null) ...[
                const SizedBox(height: 14),
                Text(
                  workflow.description,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
              if (workflow != null)
                for (final field in workflow.fields.entries) ...[
                  const SizedBox(height: 12),
                  TextField(
                    key: ValueKey('run-input-${field.key}'),
                    controller: _inputs.putIfAbsent(
                      field.key,
                      () => TextEditingController(),
                    ),
                    enabled: !_busy,
                    decoration: InputDecoration(
                      labelText: field.key.replaceAll('_', ' '),
                      helperText:
                          (field.value as Map?)?['description'] as String?,
                      helperMaxLines: 3,
                      hintText: (field.value as Map?)?['default']?.toString(),
                    ),
                  ),
                ],
              const SizedBox(height: 18),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                title: const Text('Preview mode'),
                subtitle: const Text(
                  'Validate the request without starting a workflow.',
                ),
                value: _preview,
                onChanged: _busy
                    ? null
                    : (value) => setState(() => _preview = value),
              ),
              const SizedBox(height: 14),
              const NotePanel(
                'Preview starts nothing. With Preview off, Start run is your confirmation; the working follows its configured rules.',
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 14),
                  child: Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          onPressed: _busy || selected == null ? null : () => _submit(selected),
          icon: _busy
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(LucideIcons.play, size: 16),
          label: Text(_preview ? 'Preview request' : 'Start run'),
        ),
      ],
    );
  }
}

Future<void> showRunDetail(BuildContext context, WorkflowRun run) => showDetail(
  context,
  run.workflow,
  Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Align(
        alignment: Alignment.centerLeft,
        child: StatusBadge(status: run.status),
      ),
      const SizedBox(height: 20),
      Text(run.note),
      const SizedBox(height: 18),
      DetailRow('Marketplace', run.marketplace),
      DetailRow('Started', run.started),
      DetailRow('Duration', run.duration),
      _RunControls(run),
      const SizedBox(height: 14),
      const NotePanel(
        'Latest runs on GitHub. No customer data or secret values are shown.',
      ),
    ],
  ),
);

class _RunControls extends ConsumerStatefulWidget {
  const _RunControls(this.run);
  final WorkflowRun run;
  @override
  ConsumerState<_RunControls> createState() => _RunControlsState();
}

class _RunControlsState extends ConsumerState<_RunControls> {
  bool _busy = false;
  Future<void> _execute(bool cancel) async {
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: Text(cancel ? 'Cancel this run?' : 'Run this working again?'),
        content: Text(
          cancel ? 'Already completed portal changes cannot be undone.' : 'This repeats the run with its original code and inputs. Any live portal actions can happen again.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialog, false),
            child: const Text('Back'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialog, true),
            child: Text(cancel ? 'Cancel run' : 'Run again'),
          ),
        ],
      ),
    );
    if (accepted != true || !mounted) return;
    setState(() => _busy = true);
    try {
      await ref
          .read(repositoryProvider)
          .control(
            cancel ? 'workflow.cancel' : 'workflow.rerun',
            args: {'runId': widget.run.id},
            confirmed: true,
          );
      await ref.read(workspaceProvider.notifier).refresh();
      if (mounted) {
        showNotice(
          context,
          cancel ? 'Cancellation requested.' : 'Run requested.',
        );
      }
    } on FrontendException catch (e) {
      if (mounted) showNotice(context, e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.run.controllable ||
        ref.watch(authProvider).user?.allows('workflows.run') != true) {
      return const SizedBox.shrink();
    }
    final cancel = widget.run.status == RunStatus.running;
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: OutlinedButton(
        onPressed: _busy ? null : () => _execute(cancel),
        child: Text(
          _busy
              ? 'Please wait…'
              : cancel
              ? 'Cancel run'
              : 'Run again',
        ),
      ),
    );
  }
}

Future<void> showConnectionDetail(
  BuildContext context,
  PortalConnection connection,
) => showDetail(
  context,
  '${connection.name} connection',
  Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(connection.detail),
      const SizedBox(height: 18),
      DetailRow('Status', connection.available ? 'Connected' : 'Needs login'),
      DetailRow('Last check', connection.detail),
      const SizedBox(height: 18),
      const Text(
        'Reconnect through the supported owner login process. Any human verification remains manual. Saved credentials stay hidden.',
      ),
      const SizedBox(height: 18),
      const NotePanel(
        'Portal reconnection is not wired in this frontend. App sign-out is separate from marketplace logout.',
      ),
    ],
  ),
);

Future<void> showReportDetail(BuildContext context, ReportFile report) =>
    showDetail(
      context,
      report.name,
      Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(report.updated, style: Theme.of(context).textTheme.bodySmall),
          const SectionHeading('Source coverage'),
          for (final source in report.sources)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    source.available
                        ? LucideIcons.circleCheck
                        : LucideIcons.circleAlert,
                    size: 18,
                    color: source.available
                        ? Theme.of(context).colorScheme.primary
                        : const Color(0xFF9E681D),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          source.name,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        if (source.note != null)
                          Text(
                            source.note!,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    source.available ? 'Included' : 'Excluded',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          const SizedBox(height: 16),
          NotePanel(
            report.isPartial
                ? 'Unavailable figures are excluded, never represented as zero.'
                : 'All listed sources are included in this report.',
          ),
          const SizedBox(height: 18),
          OutlinedButton.icon(
            onPressed: () => showNotice(
              context,
              'File access will be available after the authenticated report API is connected.',
            ),
            icon: const Icon(LucideIcons.externalLink, size: 17),
            label: const Text('Open workbook'),
          ),
        ],
      ),
    );

class DetailRow extends StatelessWidget {
  const DetailRow(this.label, this.value, {super.key});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 10),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Text(label, style: Theme.of(context).textTheme.bodySmall),
        ),
        const SizedBox(width: 12),
        Flexible(
          child: Text(
            value,
            textAlign: TextAlign.right,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
          ),
        ),
      ],
    ),
  );
}
