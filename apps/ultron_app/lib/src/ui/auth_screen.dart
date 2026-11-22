import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:material_ui/material_ui.dart';

import '../app_info.dart';
import '../domain/models.dart';
import '../state/providers.dart';
import 'components.dart';

enum AuthScreenMode { login, register, setup }

/// Sign in with a username and password; ask for an account (an administrator approves it); "SMS only"
/// for a phone that only sends its SMS to the sheet; and, while no administrator exists, first-time setup
/// (the setup code makes the first administrator, who chooses their own password).
class AuthScreen extends ConsumerStatefulWidget {
  const AuthScreen({super.key, this.mode = AuthScreenMode.login});
  final AuthScreenMode mode;
  @override
  ConsumerState<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends ConsumerState<AuthScreen> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  final _code = TextEditingController();
  bool _hidden = true, _busy = false, _requested = false, _setupNeeded = false;
  String? _error;

  bool get _login => widget.mode == AuthScreenMode.login;
  bool get _setup => widget.mode == AuthScreenMode.setup;

  @override
  void initState() {
    super.initState();
    if (_login) {
      ref.read(repositoryProvider).setupNeeded().then((needed) {
        if (mounted) setState(() => _setupNeeded = needed);
      });
    }
  }

  @override
  void dispose() {
    for (final c in [_name, _username, _password, _confirm, _code]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    if (_login) {
      await ref
          .read(authProvider.notifier)
          .signIn(_username.text, _password.text);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final repo = ref.read(repositoryProvider);
      if (_setup) {
        await repo.firstAdmin(
          code: _code.text,
          name: _name.text,
          username: _username.text,
          password: _password.text,
        );
        // the first administrator signs straight in
        await ref
            .read(authProvider.notifier)
            .signIn(_username.text, _password.text);
        return;
      }
      await repo.register(_name.text, _username.text, _password.text);
      if (mounted) setState(() => _requested = true);
    } on FrontendException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String? _usernameRule(String? v) =>
      RegExp(r'^[A-Za-z0-9_.]{3,30}$').hasMatch((v ?? '').trim())
      ? null
      : '3 to 30 letters, digits, dots or underscores';

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(authProvider);
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final busy = _busy || session.busy;
    final error = _login
        ? session.error
        : (_error ?? (_setup ? session.error : null));
    final wide = MediaQuery.sizeOf(context).width >= 900;
    final title = switch (widget.mode) {
      AuthScreenMode.login => 'Sign in',
      AuthScreenMode.register => 'Ask for an account',
      AuthScreenMode.setup => 'Set up ULTRON',
    };
    final lead = switch (widget.mode) {
      AuthScreenMode.login =>
        'Use the username and password your administrator gave you.',
      AuthScreenMode.register =>
        'An administrator approves new accounts before they can open ULTRON.',
      AuthScreenMode.setup =>
        'Make the first administrator: enter the setup code you were given, then choose your own '
            'username and password.',
    };

    final form = Form(
      key: _form,
      child: AutofillGroup(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (!wide) ...[
              const Align(
                alignment: Alignment.centerLeft,
                child: BrandMark(size: 36, wordmark: true),
              ),
              const SizedBox(height: 32),
            ],
            Semantics(
              header: true,
              child: Text(title, style: theme.textTheme.headlineMedium),
            ),
            const SizedBox(height: 6),
            Text(
              lead,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: scheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 28),
            if (_requested) ...[
              const NotePanel(
                'Request sent. You can sign in once an administrator approves your account.',
              ),
              const SizedBox(height: 16),
              OutlinedButton(
                onPressed: () => context.go('/login'),
                child: const Text('Back to sign in'),
              ),
            ] else ...[
              if (_setup) ...[
                TextFormField(
                  key: const Key('setup-code'),
                  controller: _code,
                  enabled: !busy,
                  autocorrect: false,
                  textCapitalization: TextCapitalization.characters,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                    labelText: 'Setup code',
                    hintText: 'XXXX-XXXX-XXXX',
                    prefixIcon: Icon(LucideIcons.keyRound, size: 18),
                  ),
                  validator: (v) => (v ?? '').trim().length < 6
                      ? 'Enter the setup code'
                      : null,
                ),
                const SizedBox(height: 16),
              ],
              if (!_login) ...[
                TextFormField(
                  key: const Key('register-name'),
                  controller: _name,
                  enabled: !busy,
                  textInputAction: TextInputAction.next,
                  autofillHints: const [AutofillHints.name],
                  decoration: const InputDecoration(labelText: 'Full name'),
                  validator: (v) =>
                      (v ?? '').trim().length < 2 ? 'Enter your name' : null,
                ),
                const SizedBox(height: 16),
              ],
              TextFormField(
                key: const Key('auth-username'),
                controller: _username,
                enabled: !busy,
                textInputAction: TextInputAction.next,
                autocorrect: false,
                autofillHints: [
                  _login ? AutofillHints.username : AutofillHints.newUsername,
                ],
                decoration: const InputDecoration(
                  labelText: 'Username',
                  prefixIcon: Icon(LucideIcons.atSign, size: 18),
                ),
                validator: _usernameRule,
              ),
              const SizedBox(height: 16),
              TextFormField(
                key: const Key('auth-password'),
                controller: _password,
                enabled: !busy,
                obscureText: _hidden,
                textInputAction: _login
                    ? TextInputAction.done
                    : TextInputAction.next,
                autofillHints: [
                  _login ? AutofillHints.password : AutofillHints.newPassword,
                ],
                onFieldSubmitted: _login ? (_) => _submit() : null,
                decoration: InputDecoration(
                  labelText: 'Password',
                  helperText: _login ? null : 'At least 8 characters',
                  prefixIcon: const Icon(LucideIcons.lockKeyhole, size: 18),
                  suffixIcon: IconButton(
                    tooltip: _hidden ? 'Show password' : 'Hide password',
                    onPressed: () => setState(() => _hidden = !_hidden),
                    icon: Icon(
                      _hidden ? LucideIcons.eye : LucideIcons.eyeOff,
                      size: 18,
                    ),
                  ),
                ),
                validator: (v) => (v ?? '').length < (_login ? 1 : 8)
                    ? (_login ? 'Enter your password' : 'At least 8 characters')
                    : null,
              ),
              if (!_login) ...[
                const SizedBox(height: 16),
                TextFormField(
                  key: const Key('register-confirm'),
                  controller: _confirm,
                  enabled: !busy,
                  obscureText: _hidden,
                  onFieldSubmitted: (_) => _submit(),
                  decoration: const InputDecoration(
                    labelText: 'Password again',
                  ),
                  validator: (v) =>
                      v != _password.text ? 'The passwords differ' : null,
                ),
              ],
              if (error != null) ...[
                const SizedBox(height: 16),
                Semantics(
                  liveRegion: true,
                  child: NotePanel(error, warning: true),
                ),
              ],
              const SizedBox(height: 24),
              GradientButton(
                key: const Key('auth-submit'),
                label: switch (widget.mode) {
                  AuthScreenMode.login => 'Sign in',
                  AuthScreenMode.register => 'Send request',
                  AuthScreenMode.setup => 'Create administrator',
                },
                busy: busy,
                onPressed: _submit,
              ),
              const SizedBox(height: 12),
              TextButton(
                onPressed: busy
                    ? null
                    : () => context.go(_login ? '/register' : '/login'),
                child: Text(_login ? 'Ask for an account' : 'Back to sign in'),
              ),
              if (_login && _setupNeeded) ...[
                const SizedBox(height: 8),
                FilledButton.tonalIcon(
                  key: const Key('first-setup'),
                  onPressed: busy ? null : () => context.go('/setup'),
                  icon: const Icon(LucideIcons.shieldPlus, size: 18),
                  label: const Text('First-time setup: make the administrator'),
                ),
              ],
              if (_login) ...[
                const SizedBox(height: 8),
                const Divider(),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  key: const Key('sms-only'),
                  onPressed: busy ? null : () => context.go('/sms'),
                  icon: const Icon(LucideIcons.messageSquareShare, size: 18),
                  label: const Text('SMS only (no account)'),
                ),
              ],
            ],
            const SizedBox(height: 32),
            Text(
              'Developed by ${AppInfo.developer}',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(
                color: scheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );

    final formPane = SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: form,
          ),
        ),
      ),
    );

    return Scaffold(
      body: wide
          ? Row(
              children: [
                Expanded(
                  child: Container(
                    color: scheme.surfaceContainer,
                    padding: const EdgeInsets.all(48),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const BrandMark(size: 36, wordmark: true),
                        const Spacer(),
                        Text(
                          'Operations, in one place.',
                          style: theme.textTheme.headlineMedium,
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'Users and access, the agent\'s model and memory, and the phones that send '
                          'their SMS to the sheet.',
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: scheme.onSurfaceVariant,
                          ),
                        ),
                        const Spacer(),
                        Text(
                          '${AppInfo.name} · Ecom Manager',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                ),
                Expanded(child: formPane),
              ],
            )
          : formPane,
    );
  }
}
