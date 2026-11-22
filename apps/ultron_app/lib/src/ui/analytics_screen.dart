import 'package:material_ui/material_ui.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../theme/app_theme.dart';
import 'components.dart';

class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key});
  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  String _period = 'Week';
  static const datasets = <String, List<(String, int)>>{
    'Week': [
      ('M', 20),
      ('T', 25),
      ('W', 18),
      ('T', 26),
      ('F', 27),
      ('S', 28),
      ('S', 24),
    ],
    'Month': [('W1', 140), ('W2', 151), ('W3', 160), ('W4', 168)],
    'Year': [('Q1', 1740), ('Q2', 1832), ('Q3', 1924), ('Q4', 1860)],
  };

  @override
  Widget build(BuildContext context) {
    final values = datasets[_period]!;
    final total = values.fold<int>(0, (sum, row) => sum + row.$2);
    final ceiling =
        values.map((row) => row.$2).reduce((a, b) => a > b ? a : b) * 1.12;
    final scheme = Theme.of(context).colorScheme;
    return PageBody(
      maxWidth: 960,
      children: [
        const PageHeading(
          'Run analytics',
          subtitle: 'Illustrative run history · Completed runs',
        ),
        SegmentedButton<String>(
          segments: ['Week', 'Month', 'Year']
              .map(
                (period) => ButtonSegment(value: period, label: Text(period)),
              )
              .toList(),
          selected: {_period},
          onSelectionChanged: (values) =>
              setState(() => _period = values.first),
          showSelectedIcon: false,
        ),
        const SizedBox(height: 28),
        Text('Completed runs', style: Theme.of(context).textTheme.bodySmall),
        Text(
          '$total',
          style: Theme.of(context).textTheme.headlineLarge
              ?.copyWith(fontSize: 38),
        ),
        const SizedBox(height: 5),
        Text(
          '$_period view · Synthetic history',
          style: TextStyle(color: scheme.primary, fontSize: 12),
        ),
        const SizedBox(height: 30),
        SizedBox(
          height: 230,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (var index = 0; index < values.length; index++)
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 9),
                    child: Semantics(
                      label:
                          '${values[index].$1}: ${values[index].$2} completed runs',
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          Text(
                            '${values[index].$2}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          const SizedBox(height: 7),
                          Container(
                            height: 162 * values[index].$2 / ceiling,
                            constraints: const BoxConstraints(maxWidth: 48),
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(6),
                              gradient: const LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: [Color(0xFF16B274), Brand.green],
                              ),
                            ),
                          ),
                          const SizedBox(height: 12),
                          Text(
                            values[index].$1,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        const SectionHeading('By marketplace · Example week'),
        for (final (portal, count, goal) in [
          ('Myntra', 72, 80),
          ('AJIO', 56, 56),
          ('Flipkart', 40, 42),
        ])
          Padding(
            padding: const EdgeInsets.only(bottom: 20),
            child: Row(
              children: [
                PortalIcon(portal),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              portal,
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          Text(
                            '$count / $goal',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                      const SizedBox(height: 9),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: LinearProgressIndicator(
                          value: count / goal,
                          minHeight: 7,
                          backgroundColor: scheme.outlineVariant.withValues(
                            alpha: .5,
                          ),
                          color: scheme.primary,
                          semanticsLabel:
                              '$portal completed $count of $goal runs',
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: 15),
        const NotePanel(
          'Partial sources stay clearly marked. These analytics are sample data.',
        ),
        const SizedBox(height: 15),
        OutlinedButton.icon(
          onPressed: () => showDetail(
            context,
            'Exact chart values',
            Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (var index = 0; index < values.length; index++)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 7),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            'Period ${index + 1} · ${values[index].$1}',
                          ),
                        ),
                        Text('${values[index].$2} runs'),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          icon: const Icon(LucideIcons.table2, size: 17),
          label: const Text('View chart values'),
        ),
      ],
    );
  }
}
