import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../state/providers.dart';
import '../domain/access.dart';
import '../theme/app_theme.dart';
import 'components.dart';

typedef AppDestination = ({String label, String path, IconData icon});

const destinations = <AppDestination>[
  (label: 'Home', path: '/app/home', icon: LucideIcons.house),
  (label: 'Agent', path: '/app/agent', icon: LucideIcons.messageCircle),
  (label: 'Workflows', path: '/app/workflows', icon: LucideIcons.layers),
  (
    label: 'Reports',
    path: '/app/reports',
    icon: LucideIcons.chartNoAxesColumnIncreasing,
  ),
  (label: 'Profile', path: '/app/profile', icon: LucideIcons.userRound),
];

const secondaryDestinations = <AppDestination>[
  (label: 'Approvals', path: '/app/approvals', icon: LucideIcons.shieldCheck),
  (
    label: 'Analytics',
    path: '/app/analytics',
    icon: LucideIcons.chartNoAxesCombined,
  ),
  (label: 'Phone Work', path: '/app/phone', icon: LucideIcons.smartphone),
  (label: 'Connections', path: '/app/connections', icon: LucideIcons.plug),
  (label: 'Schedule', path: '/app/schedule', icon: LucideIcons.calendarDays),
  (label:'Control panel',path:'/app/control',icon:LucideIcons.slidersHorizontal),
  (label:'Users',path:'/app/admin',icon:LucideIcons.users),
  (label:'Roles',path:'/app/roles',icon:LucideIcons.shieldCheck),
];

class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.location, required this.child});
  final String location;
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user=ref.watch(authProvider).user;
    final navigation=destinations.where((item){final p=permissionForPath(item.path);return p==null || user?.allows(p)==true;}).toList();
    final selected=navigation.indexWhere((item)=>item.path==location);
    final scheme = Theme.of(context).colorScheme;
    final wide = MediaQuery.sizeOf(context).width >= 900;
    final rail = MediaQuery.sizeOf(context).width >= 650;
    final title =
        [
          ...destinations,
          ...secondaryDestinations,
        ].where((item) => item.path == location).firstOrNull?.label ??
        'Workspace';
    return Scaffold(
      appBar: wide
          ? null
          : AppBar(
              automaticallyImplyLeading: false,
              title: location == '/app/home'
                  ? const BrandMark(wordmark: true, size: 28)
                  : Text(title, style: Theme.of(context).textTheme.titleLarge),
              actions: [
                IconButton(
                  tooltip: 'Approvals',
                  onPressed: canAccess(ref,'approvals.read') ? () => context.go('/app/approvals') : null,
                  icon: const Icon(LucideIcons.bell, size: 21),
                ),
                const SizedBox(width: 8),
              ],
            ),
      body: SafeArea(
        top: !wide,
        child: Row(
          children: [
            if (rail)
              Container(
                width: wide ? 224 : 78,
                decoration: BoxDecoration(
                  color: scheme.surface,
                  border: Border(
                    right: BorderSide(
                      color: scheme.outlineVariant.withValues(alpha: .5),
                    ),
                  ),
                ),
                child: Material(
                  color: scheme.surface,
                  child: _Sidebar(location: location, extended: wide),
                ),
              ),
            Expanded(
              child: Column(
                children: [
                  if (wide)
                    Container(
                      height: 64,
                      padding: const EdgeInsets.symmetric(horizontal: 32),
                      decoration: BoxDecoration(
                        border: Border(
                          bottom: BorderSide(
                            color: scheme.outlineVariant.withValues(alpha: .5),
                          ),
                        ),
                      ),
                      child: Row(
                        children: [
                          Text(
                            ref.watch(repositoryProvider).isDemo?'Demo workspace':'Workspace',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          const Padding(
                            padding: EdgeInsets.symmetric(horizontal: 12),
                            child: Icon(LucideIcons.chevronRight, size: 14),
                          ),
                          Text(
                            title,
                            style: Theme.of(context).textTheme.bodyMedium,
                          ),
                          const Spacer(),
                          IconButton(
                            tooltip: 'Review approvals',
                            onPressed: canAccess(ref,'approvals.read') ? () => context.go('/app/approvals') : null,
                            icon: const Icon(LucideIcons.bell, size: 20),
                          ),
                          const SizedBox(width: 12),
                          const _OwnerAvatar(),
                        ],
                      ),
                    ),
                  if (ref.watch(repositoryProvider).isDemo)
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 20,
                        vertical: 7,
                      ),
                      color: scheme.primary.withValues(alpha: .055),
                      child: Row(
                        children: [
                          Icon(
                            LucideIcons.flaskConical,
                            size: 13,
                            color: scheme.primary,
                          ),
                          const SizedBox(width: 7),
                          Expanded(
                            child: Text(
                              'Demo workspace · Sample data · No live actions',
                              style: TextStyle(
                                fontSize: 11,
                                color: scheme.onSurfaceVariant,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  Expanded(child: child),
                ],
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: rail
          ? null
          : NavigationBar(
              selectedIndex: selected<0?navigation.length-1:selected,
              onDestinationSelected: (index) =>
                  context.go(navigation[index].path),
              destinations: navigation
                  .map(
                    (item) => NavigationDestination(
                      icon: Icon(item.icon, size: 21),
                      selectedIcon: Icon(
                        item.icon,
                        size: 21,
                        color: scheme.primary,
                      ),
                      label: item.label == 'Workflows' ? 'Work' : item.label,
                    ),
                  )
                  .toList(),
            ),
    );
  }
}

class _Sidebar extends ConsumerWidget {
  const _Sidebar({required this.location, required this.extended});
  final String location;
  final bool extended;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Column(
      children: [
        Padding(
          padding: EdgeInsets.symmetric(
            horizontal: extended ? 24 : 19,
            vertical: 30,
          ),
          child: BrandMark(wordmark: extended, size: 34),
        ),
        if (extended)
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 23),
            child: Row(
              children: [
                const Icon(LucideIcons.building2, size: 16),
                const SizedBox(width: 9),
                Expanded(
                  child: Text(
                    ref.watch(repositoryProvider).isDemo?'Demo workspace':'Workspace',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
                const Icon(LucideIcons.chevronsUpDown, size: 14),
              ],
            ),
          ),
        Expanded(
          child: SingleChildScrollView(
            child: Column(
              children: [
                for (final item in [
                  ...destinations.take(4),
                  ...secondaryDestinations,
                ].where((item){final permission=permissionForPath(item.path);return permission==null || ref.watch(authProvider).user?.allows(permission)==true;}))
                  _NavigationEntry(
                    item: item,
                    selected: item.path == location,
                    extended: extended,
                  ),
              ],
            ),
          ),
        ),
        const Divider(),
        Padding(
          padding: const EdgeInsets.all(12),
          child: ListTile(
            contentPadding: EdgeInsets.symmetric(horizontal: extended ? 12 : 0),
            leading: extended ? const _OwnerAvatar() : null,
            title: extended
                ? Text(
                    ref.watch(authProvider).user?.name??'Account',
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                  )
                : const Icon(LucideIcons.userRound, size: 21),
            subtitle: extended
                ? const Text(
                    'Profile & settings',
                    style: TextStyle(fontSize: 11),
                  )
                : null,
            onTap: () => context.go('/app/profile'),
          ),
        ),
      ],
    );
  }
}

class _OwnerAvatar extends StatelessWidget {
  const _OwnerAvatar();
  @override
  Widget build(BuildContext context) => CircleAvatar(
    radius: 18,
    backgroundColor: Theme.of(context).colorScheme.primary
        .withValues(alpha: .09),
    child: const Text(
      'OW',
      style: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w700,
        color: Brand.green,
      ),
    ),
  );
}

class _NavigationEntry extends ConsumerWidget {
  const _NavigationEntry({
    required this.item,
    required this.selected,
    required this.extended,
  });
  final AppDestination item;
  final bool selected;
  final bool extended;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final count = ref.watch(workspaceProvider).asData?.value.pendingApprovals;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 3),
      child: Material(
        color: selected
            ? scheme.primary.withValues(alpha: .1)
            : Colors.transparent,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => context.go(item.path),
          child: Tooltip(
            message: extended ? '' : item.label,
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: extended ? 14 : 15,
                vertical: 13,
              ),
              child: Row(
                children: [
                  Icon(
                    item.icon,
                    size: 20,
                    color: selected ? scheme.primary : scheme.onSurfaceVariant,
                  ),
                  if (extended) ...[
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        item.label,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: selected
                              ? FontWeight.w600
                              : FontWeight.w400,
                        ),
                      ),
                    ),
                    if (item.label == 'Approvals' && count != null)
                      Text(
                        '$count',
                        style: TextStyle(color: scheme.primary, fontSize: 12),
                      ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
