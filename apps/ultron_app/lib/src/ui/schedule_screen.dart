import 'package:material_ui/material_ui.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'components.dart';

class ScheduleScreen extends StatelessWidget {
  const ScheduleScreen({super.key});
  @override
  Widget build(BuildContext context) => PageBody(
    maxWidth: 900,
    children: [
      const PageHeading(
        'Schedule',
        subtitle: 'Representative working schedule · Asia/Kolkata',
      ),
      const NotePanel(
        'Example schedule, not a live scheduler. Canonical rules remain in the existing worker.',
      ),
      const SizedBox(height: 22),
      for (final (time, title, note) in [
        (
          '09:00',
          'AJIO SPF master',
          'Tickets and replies only Wednesday + Saturday.',
        ),
        ('09:30', 'Morning sale & Myntra reports', 'Daily reporting snapshot.'),
        (
          '10:00',
          'Myntra SPF master',
          'Daily · Claims remain alive until received or paid.',
        ),
        ('11:00', 'Courier OTPs', 'Myntra · Daily.'),
        ('11:30', 'Listing health', 'All marketplaces.'),
        ('12:00', 'Dispatch SLA', 'Second check at 15:00 IST.'),
        ('17:30', 'AJIO TAT, VMS & portal sale', 'Daily evening operations.'),
        ('20:00', 'Evening summary', 'Daily owner report.'),
      ])
        Padding(
          padding: const EdgeInsets.only(bottom: 13),
          child: Card(
            child: ListTile(
              contentPadding: const EdgeInsets.all(16),
              leading: const PortalIcon('All', icon: LucideIcons.calendarDays),
              title: Text(
                title,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              subtitle: Padding(
                padding: const EdgeInsets.only(top: 5),
                child: Text(note, style: const TextStyle(fontSize: 12)),
              ),
              trailing: Text(
                time,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
        ),
    ],
  );
}
