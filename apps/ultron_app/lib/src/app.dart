import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'router.dart';
import 'state/providers.dart';
import 'theme/app_theme.dart';

class UltronApp extends ConsumerWidget {
  const UltronApp({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp.router(
    title: 'ULTRON · Ecom Manager',
    debugShowCheckedModeBanner: false,
    theme: Brand.theme(Brightness.light),
    darkTheme: Brand.theme(Brightness.dark),
    themeMode: ref.watch(themeModeProvider),
    routerConfig: ref.watch(routerProvider),
  );
}
