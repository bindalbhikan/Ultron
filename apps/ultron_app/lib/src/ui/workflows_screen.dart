import 'package:material_ui/material_ui.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../domain/models.dart';
import 'actions.dart';
import 'components.dart';

class WorkflowsScreen extends StatefulWidget {
  const WorkflowsScreen({super.key});
  @override
  State<WorkflowsScreen> createState() => _WorkflowsScreenState();
}

class _WorkflowsScreenState extends State<WorkflowsScreen> {
  String _portal = 'All';
  String _query = '';
  @override
  Widget build(BuildContext context) => DataGate(
    builder: (data) {
      final workflows = data.workflows
          .where(
            (item) =>
                (_portal == 'All' || item.marketplace == _portal) &&
                item.name.toLowerCase().contains(_query.toLowerCase()),
          )
          .toList();
      return PageBody(
        children: [
          PageHeading(
            'Workflows',
            subtitle: 'Your scheduled and on-demand workings.',
            trailing: IconButton(
              tooltip: 'Run workflow',
              onPressed: () => showRunWorkflow(context),
              icon: const Icon(LucideIcons.circlePlus),
            ),
          ),
          TextField(
            key: const Key('workflow-search'),
            decoration: const InputDecoration(
              hintText: 'Search workflows',
              prefixIcon: Icon(LucideIcons.search, size: 19),
            ),
            onChanged: (value) => setState(() => _query = value),
          ),
          const SizedBox(height: 17),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: ['All', 'Myntra', 'AJIO', 'Flipkart']
                .map(
                  (portal) => ChoiceChip(
                    label: Text(portal),
                    selected: _portal == portal,
                    showCheckmark: false,
                    selectedColor: Theme.of(context).colorScheme.primary,
                    labelStyle: TextStyle(
                      color: _portal == portal
                          ? Theme.of(context).colorScheme.onPrimary
                          : Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                    onSelected: (_) => setState(() => _portal = portal),
                  ),
                )
                .toList(),
          ),
          const SizedBox(height: 22),
          if (workflows.isEmpty)
            const Padding(
              padding: EdgeInsets.all(30),
              child: Text('No matching workflows. Try another search.'),
            ),
          for (final workflow in workflows) _WorkflowTile(workflow: workflow),
          const SizedBox(height: 24),
          Align(
            alignment: Alignment.center,
            child: SizedBox(
              width: 340,
              child: GradientButton(
                label: 'Run workflow',
                icon: LucideIcons.play,
                onPressed: () => showRunWorkflow(context),
              ),
            ),
          ),
        ],
      );
    },
  );
}

class _WorkflowTile extends StatelessWidget {
  const _WorkflowTile({required this.workflow});
  final Workflow workflow;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: () => showRunWorkflow(context, workflow: workflow),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 6),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            PortalIcon(
              workflow.marketplace,
              icon: workflow.id == 'inventory' ? LucideIcons.boxes : null,
            ),
            const SizedBox(width: 13),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    workflow.name,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Wrap(
                    spacing: 9,
                    runSpacing: 4,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      StatusBadge(status: workflow.status),
                      Text(
                        workflow.updated,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                  const SizedBox(height: 7),
                  Text(
                    workflow.schedule,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            const Padding(
              padding: EdgeInsets.only(top: 5),
              child: Icon(LucideIcons.chevronRight, size: 17),
            ),
          ],
        ),
      ),
    ),
  );
}
