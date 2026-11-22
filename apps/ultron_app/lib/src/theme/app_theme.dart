import 'package:material_ui/material_ui.dart';

/// ULTRON's design tokens: a dark operations look (slate surfaces, status green), from the
/// ui-ux-pro-max design system for an ops / admin product, with a light variant of the same roles.
/// Text pairs meet WCAG 4.5:1 in both modes; touch targets are 48dp; body text is 14-16px.
abstract final class Brand {
  // dark (default)
  static const ink = Color(0xFF0F172A); // background
  static const card = Color(0xFF1B2336);
  static const raised = Color(0xFF272F42); // muted surface, inputs
  static const line = Color(0xFF475569); // borders
  static const text = Color(0xFFF8FAFC);
  static const textMuted = Color(0xFF94A3B8);
  static const green = Color(0xFF22C55E); // accent / primary action
  static const onGreen = Color(0xFF0F172A);
  static const amber = Color(0xFFF59E0B);
  static const red = Color(0xFFEF4444);

  // light
  static const paper = Color(0xFFF8FAFC);
  static const lightLine = Color(0xFFCBD5E1);
  static const lightText = Color(0xFF0F172A);
  static const lightMuted = Color(0xFF475569);
  static const deepGreen = Color(0xFF15803D); // green on white at 5:1

  static ThemeData theme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final scheme = ColorScheme(
      brightness: brightness,
      primary: dark ? green : deepGreen,
      onPrimary: dark ? onGreen : Colors.white,
      secondary: dark ? const Color(0xFF334155) : const Color(0xFFE2E8F0),
      onSecondary: dark ? text : lightText,
      error: dark ? red : const Color(0xFFB91C1C),
      onError: dark ? Colors.black : Colors.white,
      surface: dark ? ink : paper,
      onSurface: dark ? text : lightText,
      onSurfaceVariant: dark ? textMuted : lightMuted,
      surfaceContainerLowest: dark ? ink : Colors.white,
      surfaceContainerLow: dark ? card : Colors.white,
      surfaceContainer: dark ? card : Colors.white,
      surfaceContainerHigh: dark ? raised : const Color(0xFFF1F5F9),
      surfaceContainerHighest: dark ? raised : const Color(0xFFE2E8F0),
      outline: dark ? line : lightLine,
      outlineVariant: dark ? const Color(0xFF334155) : const Color(0xFFE2E8F0),
      tertiary: amber,
      onTertiary: Colors.black,
    );
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      fontFamily: 'DMSans',
      materialTapTargetSize: MaterialTapTargetSize.padded,
      visualDensity: VisualDensity.standard,
    );
    final radius = BorderRadius.circular(12);
    return base.copyWith(
      scaffoldBackgroundColor: scheme.surface,
      textTheme: base.textTheme
          .copyWith(
            headlineMedium: base.textTheme.headlineMedium?.copyWith(
              fontSize: 26,
              fontWeight: FontWeight.w700,
              letterSpacing: -.5,
            ),
            titleLarge: base.textTheme.titleLarge?.copyWith(
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
            titleMedium: base.textTheme.titleMedium?.copyWith(
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
            titleSmall: base.textTheme.titleSmall?.copyWith(
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
            bodyLarge: base.textTheme.bodyLarge?.copyWith(
              fontSize: 16,
              height: 1.5,
            ),
            bodyMedium: base.textTheme.bodyMedium?.copyWith(
              fontSize: 14,
              height: 1.5,
            ),
            bodySmall: base.textTheme.bodySmall?.copyWith(
              fontSize: 13,
              height: 1.45,
            ),
            labelLarge: base.textTheme.labelLarge?.copyWith(
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          )
          .apply(bodyColor: scheme.onSurface, displayColor: scheme.onSurface),
      cardTheme: CardThemeData(
        color: scheme.surfaceContainer,
        elevation: 0,
        margin: const EdgeInsets.only(bottom: 12),
        shape: RoundedRectangleBorder(
          borderRadius: radius,
          side: BorderSide(color: scheme.outlineVariant),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surfaceContainerHigh,
        border: OutlineInputBorder(
          borderRadius: radius,
          borderSide: BorderSide(color: scheme.outline),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: radius,
          borderSide: BorderSide(color: scheme.outline),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: radius,
          borderSide: BorderSide(color: scheme.primary, width: 2),
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 14,
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, 48),
          shape: RoundedRectangleBorder(borderRadius: radius),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(48, 48),
          side: BorderSide(color: scheme.outline),
          shape: RoundedRectangleBorder(borderRadius: radius),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(minimumSize: const Size(48, 48)),
      ),
      chipTheme: base.chipTheme.copyWith(
        labelStyle: TextStyle(fontSize: 13, color: scheme.onSurface),
        side: BorderSide(color: scheme.outline),
        backgroundColor: scheme.surfaceContainerHigh,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: scheme.surfaceContainer,
        indicatorColor: scheme.primary.withValues(alpha: .18),
        labelTextStyle: WidgetStatePropertyAll(
          TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: scheme.onSurface,
          ),
        ),
      ),
      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: scheme.surfaceContainer,
        indicatorColor: scheme.primary.withValues(alpha: .18),
      ),
      dividerTheme: DividerThemeData(color: scheme.outlineVariant, space: 1),
      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surface,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 0,
      ),
    );
  }
}
