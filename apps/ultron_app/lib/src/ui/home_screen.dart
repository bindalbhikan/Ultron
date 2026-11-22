import 'package:material_ui/material_ui.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../domain/models.dart';
import '../theme/app_theme.dart';
import 'actions.dart';
import 'components.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) => DataGate(
    builder: (data) => PageBody(
      children: [
        Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Good morning,',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Workspace owner',
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                ],
              ),
            ),
            CircleAvatar(
              radius: 21,
              backgroundColor: Theme.of(context).colorScheme.primary
                  .withValues(alpha: .10),
              child: const Text(
                'OW',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: Brand.green,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),
        LayoutBuilder(
          builder: (context, constraints) {
            final main = Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _OperationsCard(data: data),
                const SizedBox(height: 22),
                const _QuickActions(),
                SectionHeading(
                  'Recent activity',
                  action: 'See all',
                  onAction: () => context.go('/app/workflows'),
                ),
                for (final run in data.runs.take(
                  constraints.maxWidth > 700 ? 5 : 3,
                ))
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _RunTile(run: run),
                  ),
                const SizedBox(height: 8),
                NotePanel(
                  'Myntra MAIN needs sign-in. Its figures are excluded.',
                  warning: true,
                  action: 'Review connection',
                  onAction: () => context.go('/app/connections'),
                ),
              ],
            );
            final secondary = _HomeContext(data: data);
            if (constraints.maxWidth < 860) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [main, secondary],
              );
            }
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(flex: 8, child: main),
                const SizedBox(width: 26),
                Expanded(flex: 5, child: secondary),
              ],
            );
          },
        ),
      ],
    ),
  );
}

class _OperationsCard extends StatelessWidget {
  const _OperationsCard({required this.data});
  final WorkspaceData data;
  @override
  Widget build(BuildContext context) => EmeraldPanel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          "Today's operations",
          style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
        ),
        const SizedBox(height: 15),
        LayoutBuilder(
          builder: (context, constraints) {
            final count = Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${data.completedRuns} / ${data.runs.length}',
                  style: const TextStyle(
                    fontSize: 42,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -1.8,
                    height: 1.1,
                  ),
                ),
                const SizedBox(height: 7),
                const Text(
                  'Runs completed',
                  style: TextStyle(fontSize: 12, color: Color(0xFFD8F3E7)),
                ),
              ],
            );
            final states = Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _StatePill(
                  icon: LucideIcons.play,
                  text: '${data.activeRuns} running',
                ),
                const SizedBox(height: 7),
                _StatePill(
                  icon: LucideIcons.triangleAlert,
                  text: '${data.blockedRuns} needs attention',
                  warning: true,
                ),
              ],
            );
            if (constraints.maxWidth <
                300 * MediaQuery.textScalerOf(context).scale(1)) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [count, const SizedBox(height: 18), states],
              );
            }
            return Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(child: count),
                const SizedBox(width: 12),
                states,
              ],
            );
          },
        ),
      ],
    ),
  );
}

class _StatePill extends StatelessWidget {
  const _StatePill({
    required this.icon,
    required this.text,
    this.warning = false,
  });
  final IconData icon;
  final String text;
  final bool warning;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: (warning ? const Color(0xFFE3C36C) : Colors.white).withValues(
        alpha: .17,
      ),
      borderRadius: BorderRadius.circular(9),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          icon,
          size: 14,
          color: warning ? const Color(0xFFFFDD90) : const Color(0xFFA1F5C4),
        ),
        const SizedBox(width: 6),
        Flexible(
          child: Text(
            text,
            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500),
          ),
        ),
      ],
    ),
  );
}

class _QuickActions extends StatelessWidget {
  const _QuickActions();
  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      for (final (label, icon, action) in <(String, IconData, VoidCallback)>[
        ('Run', LucideIcons.play, () => showRunWorkflow(context)),
        ('Ask', LucideIcons.messageCircle, () => context.go('/app/agent')),
        (
          'Reports',
          LucideIcons.chartNoAxesColumnIncreasing,
          () => context.go('/app/reports'),
        ),
        ('Review', LucideIcons.squareCheck, () => context.go('/app/approvals')),
      ])
        Expanded(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary
                      .withValues(alpha: .08),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: IconButton(
                  tooltip: label,
                  onPressed: action,
                  padding: const EdgeInsets.all(15),
                  icon: Icon(
                    icon,
                    color: Theme.of(context).colorScheme.primary,
                    size: 23,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                label,
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
    ],
  );
}

class _RunTile extends StatelessWidget {
  const _RunTile({required this.run});
  final WorkflowRun run;
  @override
  Widget build(BuildContext context) => Card(
    child: InkWell(
      borderRadius: BorderRadius.circular(18),
      onTap: () => showRunDetail(context, run),
      child: Padding(
        padding: const EdgeInsets.all(13),
        child: Row(
          children: [
            PortalIcon(
              run.marketplace,
              size: 37,
              icon: run.marketplace == 'All' ? LucideIcons.fileText : null,
            ),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    run.workflow,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    run.started,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            StatusBadge(status: run.status),
          ],
        ),
      ),
    ),
  );
}

class _HomeContext extends StatelessWidget {
  const _HomeContext({required this.data});
  final WorkspaceData data;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      SectionHeading(
        'Needs your review',
        action:
            '${data.pendingApprovals} request${data.pendingApprovals == 1 ? '' : 's'}',
        onAction: () => context.go('/app/approvals'),
      ),
      Card(
        child: Padding(
          padding: const EdgeInsets.all(19),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  PortalIcon('Myntra', size: 35),
                  SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Myntra SPF master',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Text(
                data.pendingApprovals > 0
                    ? '+12 proposed additions'
                    : 'Decision recorded',
                style: TextStyle(
                  color: Theme.of(context).colorScheme.primary,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Existing rows retained. Review the exact scope before any change.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 17),
              SizedBox(
                width: double.infinity,
                child: GradientButton(
                  label: data.pendingApprovals > 0
                      ? 'Review changes'
                      : 'View decision',
                  onPressed: () => context.go('/app/approvals'),
                ),
              ),
            ],
          ),
        ),
      ),
      SectionHeading(
        'Next scheduled',
        action: 'View',
        onAction: () => context.go('/app/schedule'),
      ),
      Card(
        child: Column(
          children: [
            for (final (time, title) in [
              ('11:00', 'Courier OTPs'),
              ('11:30', 'Listing health'),
            ])
              ListTile(
                dense: true,
                leading: const Icon(LucideIcons.calendarDays, size: 18),
                title: Text(title, style: const TextStyle(fontSize: 13)),
                subtitle: Text(
                  '$time IST · Example schedule',
                  style: const TextStyle(fontSize: 11),
                ),
                trailing: const Icon(LucideIcons.chevronRight, size: 15),
                onTap: () => context.go('/app/schedule'),
              ),
          ],
        ),
      ),
      const SectionHeading('Your phone, connected'),
      Card(
        child: ListTile(
          contentPadding: const EdgeInsets.all(16),
          leading: const PortalIcon('All', icon: LucideIcons.smartphone),
          title: const Text(
            'Phone Work',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
          ),
          subtitle: const Text(
            'Agent mode · SMS · Courier OTP & POD',
            style: TextStyle(fontSize: 11),
          ),
          trailing: const Icon(LucideIcons.chevronRight, size: 16),
          onTap: () => context.go('/app/phone'),
        ),
      ),
    ],
  );
}
