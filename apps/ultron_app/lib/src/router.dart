import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'domain/models.dart';
import 'domain/access.dart';
import 'state/providers.dart';
import 'ui/agent_screen.dart';
import 'ui/analytics_screen.dart';
import 'ui/app_shell.dart';
import 'ui/approvals_screen.dart';
import 'ui/auth_screen.dart';
import 'ui/home_screen.dart';
import 'ui/phone_screen.dart';
import 'ui/profile_screen.dart';
import 'ui/reports_screen.dart';
import 'ui/schedule_screen.dart';
import 'ui/workflows_screen.dart';
import 'ui/admin_screen.dart';
import 'ui/account_screen.dart';
import 'ui/control_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier(0);
  ref.listen(authProvider, (previous, next) => refresh.value++);
  final router = GoRouter(
    initialLocation: '/login',
    refreshListenable: refresh,
    redirect: (context, state) {
      final phase = ref.read(authProvider).phase;
      final path = state.uri.path;
      final protected = path.startsWith('/app');
      if (phase == SessionPhase.signedOut && (protected || path == '/verify' || path == '/access')) {
        return '/login';
      }
      if (phase == SessionPhase.verification && path != '/verify') {
        return '/verify';
      }
      if (phase == SessionPhase.signedIn) {
        final user=ref.read(authProvider).user;
        if(user?.hasAppAccess!=true && path!='/access')return '/access';
        if(user?.hasAppAccess==true){
          if(!protected)return '/app/home';
          final permission=permissionForPath(path);
          if(permission!=null && !user!.allows(permission))return '/app/denied';
        }
      }
      return null;
    },
    routes: [
      GoRoute(path: '/', redirect: (context, state) => '/login'),
      GoRoute(path: '/login', builder: (context, state) => const AuthScreen()),
      GoRoute(path:'/register',builder:(context,state)=>const AuthScreen(mode:AuthScreenMode.register)),
      GoRoute(path:'/access',builder:(context,state)=>const AccountScreen(pending:true)),
      GoRoute(
        path: '/verify',
        builder: (context, state) =>
            const AuthScreen(mode: AuthScreenMode.verify),
      ),
      GoRoute(
        path: '/reset',
        builder: (context, state) =>
            const AuthScreen(mode: AuthScreenMode.reset),
      ),
      ShellRoute(
        builder: (context, state, child) =>
            AppShell(location: state.uri.path, child: child),
        routes: [
          GoRoute(
            path: '/app/home',
            builder: (context, state) => ref.read(repositoryProvider).isDemo ? const HomeScreen() : const AccountScreen(),
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
            path: '/app/profile',
            builder: (context, state) => ref.read(repositoryProvider).isDemo ? const ProfileScreen() : const AccountScreen(profile:true),
          ),
          GoRoute(
            path: '/app/connections',
            builder: (context, state) => const ConnectionsScreen(),
          ),
          GoRoute(
            path: '/app/phone',
            builder: (context, state) => const PhoneScreen(),
          ),
          GoRoute(
            path: '/app/schedule',
            builder: (context, state) => const ScheduleScreen(),
          ),
          GoRoute(path:'/app/admin',builder:(context,state)=>const AdminScreen()),
          GoRoute(path:'/app/roles',builder:(context,state)=>const AdminScreen(rolesOnly:true)),
          GoRoute(path:'/app/control',builder:(context,state)=>const ControlScreen()),
          GoRoute(path:'/app/denied',builder:(context,state)=>const AccountScreen(denied:true)),
        ],
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('This screen is unavailable.'),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () => context.go('/login'),
              child: const Text('Return to workspace'),
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
