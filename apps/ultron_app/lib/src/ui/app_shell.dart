import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:material_ui/material_ui.dart';

import '../domain/access.dart';
import '../state/providers.dart';
import 'components.dart';

typedef AppDestination = ({String label, String path, IconData icon});

/// Every screen with a live service; a person sees only those their role allows (at most five, so a
/// phone shows them all in its bottom bar).
const destinations = <AppDestination>[
  (label: 'Home', path: '/app/home', icon: LucideIcons.house),
  (label: 'Control', path: '/app/control', icon: LucideIcons.slidersHorizontal),
  (label: 'Users', path: '/app/admin', icon: LucideIcons.users),
  (label: 'Roles', path: '/app/roles', icon: LucideIcons.shieldCheck),
  (label: 'Profile', path: '/app/profile', icon: LucideIcons.userRound),
];

class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.location, required this.child});
  final String location;
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authProvider).user;
    final items = destinations.where((d) {
      final permission = permissionForPath(d.path);
      return permission == null || (user?.allows(permission) ?? false);
    }).toList();
    final selected = items.indexWhere((d) => location.startsWith(d.path));
    void go(int i) => context.go(items[i].path);

    if (MediaQuery.sizeOf(context).width < 760) {
      return Scaffold(
        body: SafeArea(bottom: false, child: child),
        bottomNavigationBar: NavigationBar(
          selectedIndex: selected < 0 ? 0 : selected,
          onDestinationSelected: go,
          destinations: [
            for (final d in items)
              NavigationDestination(icon: Icon(d.icon), label: d.label),
          ],
        ),
      );
    }
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: Row(
        children: [
          NavigationRail(
            extended: MediaQuery.sizeOf(context).width >= 1100,
            minExtendedWidth: 220,
            selectedIndex: selected < 0 ? null : selected,
            onDestinationSelected: go,
            leading: const Padding(
              padding: EdgeInsets.symmetric(vertical: 20),
              child: BrandMark(size: 30),
            ),
            trailing: Expanded(
              child: Align(
                alignment: Alignment.bottomCenter,
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 20),
                  child: IconButton(
                    tooltip: 'Sign out',
                    onPressed: () async {
                      await ref.read(authProvider.notifier).signOut();
                      if (context.mounted) context.go('/login');
                    },
                    icon: Icon(
                      LucideIcons.logOut,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ),
            ),
            destinations: [
              for (final d in items)
                NavigationRailDestination(
                  icon: Icon(d.icon),
                  label: Text(d.label),
                ),
            ],
          ),
          VerticalDivider(width: 1, color: scheme.outlineVariant),
          Expanded(child: child),
        ],
      ),
    );
  }
}
