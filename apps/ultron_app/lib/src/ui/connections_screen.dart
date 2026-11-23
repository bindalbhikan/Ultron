import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:material_ui/material_ui.dart';

import '../domain/models.dart';
import 'actions.dart';
import 'components.dart';

class ConnectionsScreen extends StatelessWidget {
  const ConnectionsScreen({super.key});
  @override
  Widget build(BuildContext context) => DataGate(
    builder: (data) => PageBody(
      maxWidth: 900,
      children: [
        const PageHeading(
          'Connections',
          subtitle: 'Account health without exposing credentials.',
        ),
        Card(
          child: Column(
            children: [
              for (final connection in data.connections)
                _ConnectionRow(connection: connection),
            ],
          ),
        ),
        const SizedBox(height: 22),
        const NotePanel(
          'Live: portal sessions saved by the workings, and the Agent mode phone. Cookies and keys never reach the app.',
        ),
      ],
    ),
  );
}

class _ConnectionRow extends StatelessWidget {
  const _ConnectionRow({required this.connection});
  final PortalConnection connection;
  @override
  Widget build(BuildContext context) => InkWell(
    onTap: () => showConnectionDetail(context, connection),
    borderRadius: BorderRadius.circular(16),
    child: Padding(
      padding: const EdgeInsets.all(15),
      child: Row(
        children: [
          PortalIcon(
            connection.name,
            size: 33,
            icon: connection.name == 'Google Drive' ? LucideIcons.folder : null,
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  connection.name,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (MediaQuery.textScalerOf(context).scale(1) > 1.3) ...[
                  const SizedBox(height: 8),
                  StatusBadge(
                    status: connection.available
                        ? RunStatus.completed
                        : RunStatus.blocked,
                  ),
                ],
              ],
            ),
          ),
          if (MediaQuery.textScalerOf(context).scale(1) <= 1.3) ...[
            const SizedBox(width: 8),
            StatusBadge(
              status: connection.available
                  ? RunStatus.completed
                  : RunStatus.blocked,
            ),
          ],
          const SizedBox(width: 6),
          const Icon(LucideIcons.chevronRight, size: 15),
        ],
      ),
    ),
  );
}
