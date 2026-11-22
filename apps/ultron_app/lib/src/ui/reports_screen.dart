import 'package:material_ui/material_ui.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../domain/models.dart';
import 'actions.dart';
import 'components.dart';

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});
  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  String _period = 'All reports';
  @override
  Widget build(BuildContext context) => DataGate(
    builder: (data) => PageBody(
      children: [
        const PageHeading(
          'Reports',
          subtitle: 'Workbooks with clear source coverage.',
        ),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: ['All reports', 'Daily', 'Monthly']
              .map(
                (period) => ChoiceChip(
                  label: Text(period),
                  showCheckmark: false,
                  selected: _period == period,
                  selectedColor: Theme.of(context).colorScheme.primary,
                  labelStyle: TextStyle(
                    color: _period == period
                        ? Theme.of(context).colorScheme.onPrimary
                        : null,
                  ),
                  onSelected: (_) => setState(() => _period = period),
                ),
              )
              .toList(),
        ),
        const SizedBox(height: 22),
        Container(
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.primary.withValues(alpha: .08),
            borderRadius: BorderRadius.circular(19),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Your reports, together',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 7),
                    Text(
                      'Find, review and understand your operations reports.',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              Icon(
                LucideIcons.folders,
                size: 57,
                color: Theme.of(context).colorScheme.primary,
              ),
            ],
          ),
        ),
        const SizedBox(height: 25),
        for (final report in data.reports.where(
          (item) => _period == 'All reports' || item.period == _period,
        ))
          Padding(
            padding: const EdgeInsets.only(bottom: 13),
            child: Card(
              child: InkWell(
                borderRadius: BorderRadius.circular(18),
                onTap: () => showReportDetail(context, report),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      const PortalIcon(
                        'All',
                        icon: LucideIcons.fileSpreadsheet,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              report.name,
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              report.updated,
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      StatusBadge(
                        status: report.isPartial
                            ? RunStatus.partial
                            : RunStatus.completed,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        const SizedBox(height: 12),
        const NotePanel(
          'Unavailable sources are excluded. Open a report to inspect its exact coverage.',
        ),
      ],
    ),
  );
}
