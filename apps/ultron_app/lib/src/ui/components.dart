import 'dart:math' as math;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:material_ui/material_ui.dart';

import '../theme/app_theme.dart';
import '../domain/models.dart';
import '../state/providers.dart';

/// The ULTRON mark (two linked rounded links) and, optionally, the wordmark.
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = 32, this.wordmark = false});
  final double size;
  final bool wordmark;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      label: 'ULTRON',
      child: ExcludeSemantics(
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: size,
              height: size,
              child: CustomPaint(painter: _MarkPainter(scheme.primary)),
            ),
            if (wordmark) ...[
              const SizedBox(width: 10),
              Text(
                'ULTRON',
                style: TextStyle(
                  fontSize: size * .62,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.5,
                  color: scheme.onSurface,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _MarkPainter extends CustomPainter {
  const _MarkPainter(this.color);
  final Color color;
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = size.width * .125
      ..strokeCap = StrokeCap.round;
    canvas.save();
    canvas.translate(size.width / 2, size.height / 2);
    canvas.rotate(math.pi / 5);
    for (final x in [-.17, .17]) {
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(
            center: Offset(x * size.width, 0),
            width: size.width * .43,
            height: size.height * .72,
          ),
          Radius.circular(size.width * .18),
        ),
        paint,
      );
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_MarkPainter oldDelegate) => oldDelegate.color != color;
}

/// A page's scrollable body: centred, a readable width, gutters that grow with the screen.
class PageBody extends StatelessWidget {
  const PageBody({super.key, required this.children, this.maxWidth = 1100});
  final List<Widget> children;
  final double maxWidth;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final gutter = width < 600 ? 16.0 : (width < 1024 ? 24.0 : 32.0);
    return SafeArea(
      top: false,
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(gutter, 24, gutter, 40),
        child: Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxWidth),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: children,
            ),
          ),
        ),
      ),
    );
  }
}

class PageHeading extends StatelessWidget {
  const PageHeading(
    this.title, {
    super.key,
    this.subtitle,
    Widget? action,
    Widget? trailing,
  }) : action = action ?? trailing;
  final String title;
  final String? subtitle;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(
                  header: true,
                  child: Text(title, style: theme.textTheme.headlineMedium),
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 6),
                  Text(
                    subtitle!,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
          ?action,
        ],
      ),
    );
  }
}

class SectionHeading extends StatelessWidget {
  const SectionHeading(
    this.title, {
    super.key,
    this.trailing,
    this.action,
    this.onAction,
  });
  final String title;
  final Widget? trailing;

  /// A text button at the end (when [trailing] is not given).
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 8, bottom: 12),
    child: Row(
      children: [
        Expanded(
          child: Semantics(
            header: true,
            child: Text(title, style: Theme.of(context).textTheme.titleMedium),
          ),
        ),
        if (trailing != null)
          trailing!
        else if (action != null)
          TextButton(
            onPressed: onAction,
            child: Text(action!, style: const TextStyle(fontSize: 12)),
          ),
      ],
    ),
  );
}

/// A short message in a tinted panel: information, or a warning (never colour alone: an icon too).
class NotePanel extends StatelessWidget {
  const NotePanel(
    this.text, {
    super.key,
    this.warning = false,
    this.action,
    this.onAction,
  });
  final String text;
  final bool warning;

  /// A text button under the message.
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final tone = warning ? scheme.error : scheme.primary;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: .10),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: tone.withValues(alpha: .35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            warning ? LucideIcons.triangleAlert : LucideIcons.info,
            size: 18,
            color: tone,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(text, style: Theme.of(context).textTheme.bodyMedium),
                if (action != null)
                  TextButton(
                    style: TextButton.styleFrom(padding: EdgeInsets.zero),
                    onPressed: onAction,
                    child: Text(action!, style: const TextStyle(fontSize: 12)),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// The page's main action: the emerald gradient button of the owner's reference, full width, busy while it works.
class GradientButton extends StatelessWidget {
  const GradientButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.icon = LucideIcons.arrowRight,
    this.busy = false,
  });
  final String label;
  final VoidCallback? onPressed;
  final IconData icon;
  final bool busy;
  @override
  Widget build(BuildContext context) => Container(
    height: 52,
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(14),
      gradient: const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [Color(0xFF07996E), Color(0xFF00624A)],
      ),
      boxShadow: [
        BoxShadow(
          color: Brand.green.withValues(alpha: .14),
          blurRadius: 10,
          offset: const Offset(0, 4),
        ),
      ],
    ),
    child: FilledButton(
      style: FilledButton.styleFrom(
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.white,
        disabledBackgroundColor: Colors.transparent,
        disabledForegroundColor: Colors.white70,
        shadowColor: Colors.transparent,
      ),
      onPressed: busy ? null : onPressed,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (busy)
            SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(
                strokeWidth: 2.2,
                color: Colors.white,
                semanticsLabel: '$label, working',
              ),
            )
          else ...[
            Flexible(child: Text(label, textAlign: TextAlign.center)),
            const SizedBox(width: 10),
            Icon(icon, size: 18),
          ],
        ],
      ),
    ),
  );
}

class BrandIllustration extends StatelessWidget {
  const BrandIllustration({super.key, this.height = 190});
  final double height;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: height,
    child: Center(
      child: SizedBox(
        width: 255,
        height: height,
        child: Stack(
          alignment: Alignment.center,
          children: [
            Positioned(
              bottom: 12,
              child: Container(
                width: 226,
                height: 32,
                decoration: BoxDecoration(
                  color: const Color(0xFFD6F4E4),
                  borderRadius: BorderRadius.circular(120),
                  boxShadow: [
                    BoxShadow(
                      color: Brand.green.withValues(alpha: .12),
                      blurRadius: 32,
                      offset: const Offset(0, 12),
                    ),
                  ],
                ),
              ),
            ),
            for (final (left, top, angle, colors) in [
              (38.0, 43.0, .55, [const Color(0xFF04A67C), Brand.deepGreen]),
              (
                111.0,
                14.0,
                .55,
                [const Color(0xFFBCF5BC), const Color(0xFF37A96C)],
              ),
            ])
              Positioned(
                left: left,
                top: top,
                child: Transform.rotate(
                  angle: angle,
                  child: Container(
                    width: 85,
                    height: 128,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(32),
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: colors,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: Brand.deepGreen.withValues(alpha: .16),
                          blurRadius: 16,
                          offset: const Offset(4, 12),
                        ),
                      ],
                    ),
                    child: Center(
                      child: Container(
                        width: 39,
                        height: 77,
                        decoration: BoxDecoration(
                          color: Theme.of(context).brightness == Brightness.dark
                              ? const Color(0xFF18372A)
                              : const Color(0xFFE8F9EF),
                          borderRadius: BorderRadius.circular(15),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    ),
  );
}

class EmeraldPanel extends StatelessWidget {
  const EmeraldPanel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(22),
  });
  final Widget child;
  final EdgeInsets padding;
  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: padding,
    clipBehavior: Clip.antiAlias,
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(20),
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFF079267), Color(0xFF006347), Color(0xFF004D3C)],
      ),
      boxShadow: [
        BoxShadow(
          color: Brand.green.withValues(alpha: .13),
          blurRadius: 22,
          offset: const Offset(0, 8),
        ),
      ],
    ),
    child: DefaultTextStyle.merge(
      style: const TextStyle(color: Colors.white),
      child: IconTheme(
        data: const IconThemeData(color: Colors.white),
        child: child,
      ),
    ),
  );
}

enum Tone { good, warn, bad, neutral }

/// A status word with a dot: the word carries the meaning, the colour only repeats it.
class StatusPill extends StatelessWidget {
  const StatusPill(this.label, {super.key, this.tone = Tone.neutral});
  final String label;
  final Tone tone;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final color = switch (tone) {
      Tone.good => scheme.primary,
      Tone.warn => scheme.tertiary,
      Tone.bad => scheme.error,
      Tone.neutral => scheme.onSurfaceVariant,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .12),
        borderRadius: BorderRadius.circular(99),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 7,
            height: 7,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: scheme.onSurface,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// One number on the home overview, with what it counts and, optionally, where to act on it.
class StatCard extends StatelessWidget {
  const StatCard({
    super.key,
    required this.icon,
    required this.label,
    required this.value,
    this.note,
    this.onTap,
  });
  final IconData icon;
  final String label, value;
  final String? note;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(icon, size: 20, color: scheme.primary),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(label, style: theme.textTheme.titleSmall),
                  ),
                  if (onTap != null)
                    Icon(
                      LucideIcons.chevronRight,
                      size: 18,
                      color: scheme.onSurfaceVariant,
                    ),
                ],
              ),
              const SizedBox(height: 14),
              Text(
                value,
                style: theme.textTheme.headlineMedium?.copyWith(
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
              if (note != null) ...[
                const SizedBox(height: 4),
                Text(
                  note!,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

void showNotice(BuildContext context, String message) =>
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));

class DataGate extends ConsumerWidget {
  const DataGate({super.key, required this.builder});
  final Widget Function(WorkspaceData) builder;
  @override
  Widget build(BuildContext context, WidgetRef ref) => ref
      .watch(workspaceProvider)
      .when(
        data: builder,
        loading: () => const Center(
          child: Padding(
            padding: EdgeInsets.all(48),
            child: CircularProgressIndicator(),
          ),
        ),
        error: (error, stack) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(LucideIcons.cloudOff, size: 36),
                const SizedBox(height: 14),
                Text(
                  error is FrontendException
                      ? error.message
                      : 'The workspace could not load.',
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
                OutlinedButton(
                  onPressed: () => ref.invalidate(workspaceProvider),
                  child: const Text('Try again'),
                ),
              ],
            ),
          ),
        ),
      );
}

class PortalIcon extends StatelessWidget {
  const PortalIcon(this.marketplace, {super.key, this.icon, this.size = 40});
  final String marketplace;
  final IconData? icon;
  final double size;
  @override
  Widget build(BuildContext context) {
    final (background, foreground, letter) = switch (marketplace) {
      'Myntra' => (const Color(0xFFFFE9EC), const Color(0xFFE45872), 'M'),
      'AJIO' => (const Color(0xFF25343A), Colors.white, 'A'),
      'Flipkart' => (const Color(0xFFFFDE65), const Color(0xFF1764AD), 'f'),
      _ => (Brand.mint, Brand.green, ''),
    };
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(12),
      ),
      alignment: Alignment.center,
      child: icon != null || letter.isEmpty
          ? Icon(
              icon ?? LucideIcons.fileText,
              size: size * .47,
              color: foreground,
            )
          : Text(
              letter,
              style: TextStyle(
                fontWeight: FontWeight.w800,
                fontSize: size * .55,
                color: foreground,
              ),
            ),
    );
  }
}

class StatusBadge extends StatelessWidget {
  const StatusBadge({super.key, required this.status});
  final RunStatus status;
  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      RunStatus.completed => Brand.green,
      RunStatus.running => const Color(0xFF207E9A),
      RunStatus.partial || RunStatus.blocked => Brand.amber,
      RunStatus.failed => const Color(0xFFC0392B),
      RunStatus.never => const Color(0xFF6B7280),
    };
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: dark ? .24 : .10),
        borderRadius: BorderRadius.circular(30),
      ),
      child: Text(
        status.label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: dark ? Color.lerp(color, Colors.white, .45) : color,
        ),
      ),
    );
  }
}

Future<void> showDetail(BuildContext context, String title, Widget child) =>
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: SingleChildScrollView(child: child),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
        ],
      ),
    );

/// Up to two capital letters of a person's name ("Bhikan Deshmukh" -> "BD"); "U" when it is empty.
String initialsOf(String name) {
  final words = name.trim().split(RegExp(r'\s+')).where((w) => w.isNotEmpty);
  return words.isEmpty
      ? 'U'
      : words.take(2).map((w) => w[0].toUpperCase()).join();
}
