import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import 'domain/access.dart';
import 'domain/models.dart';
import 'state/providers.dart';
import 'ui/account_screen.dart';
import 'ui/agent_screen.dart';
import 'ui/analytics_screen.dart';
import 'ui/approvals_screen.dart';
import 'ui/reports_screen.dart';
import 'ui/schedule_screen.dart';
import 'ui/workflows_screen.dart';
import 'ui/admin_screen.dart';
import 'ui/app_shell.dart';
import 'ui/auth_screen.dart';
import 'ui/connections_screen.dart';
import 'ui/control_screen.dart';
import 'ui/home_screen.dart';
import 'ui/sms_only_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier(0);
  ref.listen(authProvider, (previous, next) => refresh.value++);
  final router = GoRouter(
    initialLocation: ref.read(startPathProvider),
    refreshListenable: refresh,
    redirect: (context, state) {
      final path = state.uri.path;
      final session = ref.read(authProvider);
      // SMS only is for a phone with no one signed in; a signed-in user has the app itself
      if (path == '/sms') {
        return session.phase == SessionPhase.signedIn ? '/app/home' : null;
      }
      final protected = path.startsWith('/app') || path == '/access';
      if (session.phase == SessionPhase.signedOut) {
        return protected ? '/login' : null;
      }
      final user = session.user;
      if (user?.hasAppAccess != true) {
        return path == '/access' ? null : '/access';
      }
      if (!path.startsWith('/app')) return '/app/home';
      final permission = permissionForPath(path);
      if (permission != null && !user!.allows(permission)) return '/app/denied';
      return null;
    },
    routes: [
      GoRoute(path: '/', redirect: (context, state) => '/login'),
      GoRoute(path: '/login', builder: (context, state) => const AuthScreen()),
      GoRoute(
        path: '/register',
        builder: (context, state) =>
            const AuthScreen(mode: AuthScreenMode.register),
      ),
      GoRoute(path: '/sms', builder: (context, state) => const SmsOnlyScreen()),
      GoRoute(
        path: '/setup',
        builder: (context, state) =>
            const AuthScreen(mode: AuthScreenMode.setup),
      ),
      GoRoute(
        path: '/access',
        builder: (context, state) => const AccountScreen(pending: true),
      ),
      ShellRoute(
        builder: (context, state, child) =>
            AppShell(location: state.uri.path, child: child),
        routes: [
          GoRoute(
            path: '/app/home',
            builder: (context, state) => const HomeScreen(),
          ),
          GoRoute(
            path: '/app/agent',
            builder: (context, state) => const AgentScreen(),
          ),
          GoRoute(
            path: '/app/workflows',
            builder: (context, state) => const WorkflowsScreen(),
          ),
          GoRoute(
            path: '/app/reports',
            builder: (context, state) => const ReportsScreen(),
          ),
          GoRoute(
            path: '/app/approvals',
            builder: (context, state) => const ApprovalsScreen(),
          ),
          GoRoute(
            path: '/app/analytics',
            builder: (context, state) => const AnalyticsScreen(),
          ),
          GoRoute(
            path: '/app/connections',
            builder: (context, state) => const ConnectionsScreen(),
          ),
          GoRoute(
            path: '/app/schedule',
            builder: (context, state) => const ScheduleScreen(),
          ),
          GoRoute(
            path: '/app/control',
            builder: (context, state) => const ControlScreen(),
          ),
          GoRoute(
            path: '/app/admin',
            builder: (context, state) => const AdminScreen(),
          ),
          GoRoute(
            path: '/app/roles',
            builder: (context, state) => const AdminScreen(rolesOnly: true),
          ),
          GoRoute(
            path: '/app/profile',
            builder: (context, state) => const AccountScreen(),
          ),
          GoRoute(
            path: '/app/denied',
            builder: (context, state) => const AccountScreen(denied: true),
          ),
        ],
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('This page does not exist.'),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () => context.go('/login'),
              child: const Text('Go to ULTRON'),
            ),
          ],
        ),
      ),
    ),
  );
  ref.onDispose(() {
    router.dispose();
    refresh.dispose();
  });
  return router;
});
