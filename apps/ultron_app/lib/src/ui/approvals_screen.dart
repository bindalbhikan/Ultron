import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../domain/models.dart';
import '../state/providers.dart';
import 'actions.dart';
import 'components.dart';

class ApprovalsScreen extends StatelessWidget {
  const ApprovalsScreen({super.key});
  @override
  Widget build(BuildContext context) => DataGate(
    builder: (data) => PageBody(
      maxWidth: 940,
      children: [
        const PageHeading(
          'Approvals',
          subtitle: 'You approve every protected change.',
        ),
        EmeraldPanel(
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${data.pendingApprovals} request${data.pendingApprovals == 1 ? '' : 's'} to review',
                      style: const TextStyle(
                        fontSize: 23,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Review the scope, evidence and destination.',
                      style: TextStyle(fontSize: 12, color: Color(0xFFD7F4E5)),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 18),
              const Icon(LucideIcons.shieldCheck, size: 43),
            ],
          ),
        ),
        const SizedBox(height: 24),
        for (final request in data.approvals) _ApprovalCard(request: request),
        if (data.approvals.isEmpty)
          const Padding(
            padding: EdgeInsets.all(32),
            child: Text(
              'No approval requests. New proposals will appear here.',
            ),
          ),
      ],
    ),
  );
}

class _ApprovalCard extends StatelessWidget {
  const _ApprovalCard({required this.request});
  final ApprovalRequest request;
  @override
  Widget build(BuildContext context) {
    final pending = request.status == ApprovalStatus.pending;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(request.title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 5),
            Text(
              'Add eligible orders',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 18),
            Align(
              alignment: Alignment.centerLeft,
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 13,
                  vertical: 7,
                ),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary
                      .withValues(alpha: .09),
                  borderRadius: BorderRadius.circular(30),
                ),
                child: Text(
                  '+${request.additions} additions',
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),
            const DetailRow('Existing rows', 'Retained · None removed'),
            DetailRow('Destination', request.destination),
            const DetailRow('Requested by', 'Workspace owner'),
            const DetailRow('Expiry', '30 minutes after demo load'),
            const SizedBox(height: 18),
            OutlinedButton.icon(
              onPressed: () => showDetail(
                context,
                'Source evidence',
                const Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'This demo proposal contains 12 synthetic additions. No order references or customer data are loaded.',
                    ),
                    SizedBox(height: 16),
                    Text(
                      'A connected review must show each affected order, current eligibility, before/after state and supporting sources. Execution must re-check expiry and scope.',
                    ),
                  ],
                ),
              ),
              icon: const Icon(LucideIcons.fileText, size: 18),
              label: const Text('Review source evidence'),
            ),
            const SizedBox(height: 18),
            if (pending) ...[
              GradientButton(
                label: 'Review changes',
                onPressed: () =>
                    _review(context, request, ApprovalStatus.approved),
              ),
              TextButton(
                onPressed: () =>
                    _review(context, request, ApprovalStatus.declined),
                child: const Text('Decline'),
              ),
            ] else
              NotePanel(
                '${request.status == ApprovalStatus.approved ? 'Approved' : 'Declined'} in this demo. No workbook was changed.',
              ),
          ],
        ),
      ),
    );
  }

  void _review(
    BuildContext context,
    ApprovalRequest request,
    ApprovalStatus decision,
  ) {
    showDialog<void>(
      context: context,
      builder: (_) => _DecisionDialog(request: request, decision: decision),
    );
  }
}

class _DecisionDialog extends ConsumerStatefulWidget {
  const _DecisionDialog({required this.request, required this.decision});
  final ApprovalRequest request;
  final ApprovalStatus decision;
  @override
  ConsumerState<_DecisionDialog> createState() => _DecisionDialogState();
}

class _DecisionDialogState extends ConsumerState<_DecisionDialog> {
  bool _busy = false;
  String? _error;
  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(workspaceProvider.notifier)
          .decide(widget.request.id, widget.decision);
      if (mounted) Navigator.pop(context);
    } on FrontendException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'This decision could not be saved. Try again.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(
      widget.decision == ApprovalStatus.approved
          ? 'Review SPF additions'
          : 'Decline this request?',
    ),
    content: SizedBox(
      width: 400,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '${widget.request.additions} proposed additions · ${widget.request.destination}',
            ),
            const SizedBox(height: 16),
            const NotePanel(
              'Demo decision only. A real approval requires complete order evidence and fresh server-side validation.',
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 14),
                child: Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
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
      FilledButton(
        onPressed: _busy ? null : _submit,
        child: Text(
          _busy
              ? 'Saving…'
              : widget.decision == ApprovalStatus.approved
              ? 'Approve demo'
              : 'Decline demo',
        ),
      ),
    ],
  );
}
