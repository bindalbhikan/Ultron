import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import 'domain/access.dart';
import 'domain/models.dart';
import 'state/providers.dart';
import 'ui/account_screen.dart';
import 'ui/admin_screen.dart';
import 'ui/app_shell.dart';
import 'ui/auth_screen.dart';
import 'ui/control_screen.dart';
import 'ui/home_screen.dart';
import 'ui/sms_only_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier(0);
  ref.listen(authProvider, (previous, next) => refresh.value++);
  final router = GoRouter(
    initialLocation: '/login',
    refreshListenable: refresh,
    redirect: (context, state) {
      final path = state.uri.path;
      // SMS only needs no account: it opens whatever the session
      if (path == '/sms') return null;
      final session = ref.read(authProvider);
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
