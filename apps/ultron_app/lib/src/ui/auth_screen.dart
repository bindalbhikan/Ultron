import 'package:material_ui/material_ui.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../data/demo_repository.dart';
import '../app_info.dart';
import '../domain/models.dart';
import '../state/providers.dart';
import '../theme/app_theme.dart';
import 'components.dart';

enum AuthScreenMode { login, verify, reset, register }

class AuthScreen extends ConsumerStatefulWidget {
  const AuthScreen({super.key, this.mode = AuthScreenMode.login});
  final AuthScreenMode mode;

  @override
  ConsumerState<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends ConsumerState<AuthScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _code = TextEditingController();
  final _name = TextEditingController();
  final _confirm = TextEditingController();
  bool _registered = false;
  bool _visible = false;
  bool _resetBusy = false;
  bool _resetSent = false;
  String? _resetError;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _code.dispose();
    _name.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    if (widget.mode == AuthScreenMode.register) {
      setState(() {
        _resetBusy = true;
        _resetError = null;
      });
      try {
        await ref
            .read(repositoryProvider)
            .register(_name.text, _email.text, _password.text);
        _password.clear();
        _confirm.clear();
        if (mounted) setState(() => _registered = true);
      } on FrontendException catch (error) {
        if (mounted) setState(() => _resetError = error.message);
      } catch (_) {
        if (mounted) {
          setState(
            () => _resetError = 'Registration could not finish. Try again.',
          );
        }
      } finally {
        if (mounted) setState(() => _resetBusy = false);
      }
      return;
    }
    if (widget.mode == AuthScreenMode.verify) {
      await ref.read(authProvider.notifier).verify(_code.text);
      return;
    }
    if (widget.mode == AuthScreenMode.reset) {
      setState(() {
        _resetBusy = true;
        _resetError = null;
      });
      try {
        await ref.read(repositoryProvider).resetPassword(_email.text.trim());
        if (mounted) setState(() => _resetSent = true);
      } on FrontendException catch (error) {
        if (mounted) setState(() => _resetError = error.message);
      } catch (_) {
        if (mounted) {
          setState(
            () => _resetError = 'The request could not finish. Try again.',
          );
        }
      } finally {
        if (mounted) setState(() => _resetBusy = false);
      }
      return;
    }
    final password = _password.text;
    _password.clear();
    await ref.read(authProvider.notifier).signIn(_email.text.trim(), password);
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(authProvider);
    final demo = ref.watch(repositoryProvider).isDemo;
    final verify = widget.mode == AuthScreenMode.verify;
    final reset = widget.mode == AuthScreenMode.reset;
    final register = widget.mode == AuthScreenMode.register;
    final busy = session.busy || _resetBusy;
    final scheme = Theme.of(context).colorScheme;
    final error = reset || register ? _resetError : session.error;

    final form = ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 390),
      child: AutofillGroup(
        child: Form(
          key: _form,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (MediaQuery.sizeOf(context).width < 860) ...[
                const Align(
                  alignment: Alignment.centerLeft,
                  child: BrandMark(wordmark: true),
                ),
                if (!verify && !reset && !register)
                  const BrandIllustration(height: 205)
                else
                  const SizedBox(height: 54),
              ],
              Text(
                register
                    ? (_registered
                          ? 'Registration received'
                          : 'Create your account')
                    : verify
                    ? 'Verify your sign-in'
                    : reset
                    ? (_resetSent ? 'Check your email' : 'Reset your password')
                    : 'Welcome back',
                style: Theme.of(context).textTheme.headlineLarge,
              ),
              const SizedBox(height: 7),
              Text(
                register
                    ? 'Your administrator decides your app and agent access.'
                    : verify
                    ? 'Enter your 6-digit verification code.'
                    : reset
                    ? 'A fresh start for your workspace access.'
                    : 'Sign in to your workspace',
                style: Theme.of(context).textTheme.bodyLarge
                    ?.copyWith(color: scheme.onSurfaceVariant),
              ),
              const SizedBox(height: 27),
              if (_registered)
                const NotePanel(
                  'Your account is awaiting administrator approval. Sign in to check your access status. Registration does not grant app or agent permissions.',
                )
              else if (_resetSent)
                NotePanel(
                  demo
                      ? 'Reset request simulated. No email was sent.'
                      : 'If an account exists, a reset link will be sent.',
                )
              else if (verify) ...[
                const Text(
                  'Verification code',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 9),
                TextFormField(
                  key: const Key('verification-code'),
                  controller: _code,
                  autofocus: true,
                  keyboardType: TextInputType.number,
                  autofillHints: const [AutofillHints.oneTimeCode],
                  maxLength: 6,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 26,
                    letterSpacing: 10,
                    fontWeight: FontWeight.w600,
                  ),
                  decoration: const InputDecoration(
                    hintText: '000000',
                    counterText: '',
                  ),
                  validator: (value) =>
                      value?.length == 6 ? null : 'Enter all six digits.',
                  onFieldSubmitted: (_) => busy ? null : _submit(),
                ),
              ] else ...[
                if (register) ...[
                  const Text(
                    'Full name',
                    style: TextStyle(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 9),
                  TextFormField(
                    key: const Key('register-name'),
                    controller: _name,
                    autofillHints: const [AutofillHints.name],
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(
                      hintText: 'Your full name',
                      prefixIcon: Icon(LucideIcons.userRound, size: 19),
                    ),
                    validator: (value) =>
                        value != null &&
                            value.trim().length >= 2 &&
                            value.trim().length <= 80
                        ? null
                        : 'Enter your full name (2–80 characters).',
                  ),
                  const SizedBox(height: 22),
                ],
                const Text(
                  'Work email',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 9),
                TextFormField(
                  key: const Key('login-email'),
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  autofillHints: const [AutofillHints.username],
                  textInputAction: reset
                      ? TextInputAction.done
                      : TextInputAction.next,
                  decoration: const InputDecoration(
                    hintText: 'name@company.com',
                    prefixIcon: Icon(LucideIcons.mail, size: 19),
                  ),
                  validator: (value) =>
                      RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
                          .hasMatch(value?.trim() ?? '')
                      ? null
                      : 'Enter a valid work email.',
                  onFieldSubmitted: reset
                      ? (_) => busy ? null : _submit()
                      : null,
                ),
                if (!reset) ...[
                  const SizedBox(height: 22),
                  const Text(
                    'Password',
                    style: TextStyle(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 9),
                  TextFormField(
                    key: const Key('login-password'),
                    controller: _password,
                    obscureText: !_visible,
                    enableSuggestions: false,
                    autocorrect: false,
                    autofillHints: [
                      register
                          ? AutofillHints.newPassword
                          : AutofillHints.password,
                    ],
                    textInputAction: TextInputAction.done,
                    decoration: InputDecoration(
                      hintText: 'Enter your password',
                      prefixIcon: const Icon(LucideIcons.lockKeyhole, size: 19),
                      suffixIcon: IconButton(
                        onPressed: () => setState(() => _visible = !_visible),
                        tooltip: _visible ? 'Hide password' : 'Show password',
                        icon: Icon(
                          _visible ? LucideIcons.eyeOff : LucideIcons.eye,
                          size: 19,
                        ),
                      ),
                    ),
                    validator: (value) =>
                        value != null &&
                            value.length >= (demo && !register ? 8 : 12) &&
                            value.length <= 128
                        ? null
                        : demo && !register
                        ? 'Use at least eight characters.'
                        : 'Use 12–128 characters.',
                    onFieldSubmitted: (_) => busy ? null : _submit(),
                  ),
                  if (register) ...[
                    const SizedBox(height: 22),
                    const Text(
                      'Confirm password',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 9),
                    TextFormField(
                      key: const Key('register-confirm'),
                      controller: _confirm,
                      obscureText: !_visible,
                      enableSuggestions: false,
                      autocorrect: false,
                      autofillHints: const [AutofillHints.newPassword],
                      decoration: const InputDecoration(
                        hintText: 'Re-enter your password',
                        prefixIcon: Icon(LucideIcons.lockKeyhole, size: 19),
                      ),
                      validator: (value) => value == _password.text
                          ? null
                          : 'Passwords must match.',
                    ),
                    const SizedBox(height: 18),
                    const NotePanel(
                      'New accounts have no access until an administrator approves a role. Verify your identity directly with your administrator; email verification is not configured yet.',
                    ),
                  ],
                  if (!register)
                    Align(
                      alignment: Alignment.centerRight,
                      child: TextButton(
                        onPressed: busy ? null : () => context.go('/reset'),
                        child: const Text('Forgot password?'),
                      ),
                    ),
                ],
              ],
              if (error != null) ...[
                const SizedBox(height: 12),
                Semantics(
                  liveRegion: true,
                  child: Text(error, style: TextStyle(color: scheme.error)),
                ),
              ],
              const SizedBox(height: 20),
              if (!_resetSent && !_registered)
                GradientButton(
                  key: const Key('auth-submit'),
                  label: register
                      ? 'Request an account'
                      : verify
                      ? 'Verify & sign in'
                      : reset
                      ? 'Send reset link'
                      : 'Sign in',
                  busy: busy,
                  onPressed: _submit,
                ),
              if (!verify && !reset && !register) ...[
                const SizedBox(height: 12),
                TextButton(
                  onPressed: busy ? null : () => context.go('/register'),
                  child: const Text('Create an account'),
                ),
              ],
              if (verify || reset || register) ...[
                const SizedBox(height: 12),
                TextButton(
                  onPressed: busy
                      ? null
                      : () async {
                          await ref.read(authProvider.notifier).signOut();
                          if (context.mounted) context.go('/login');
                        },
                  child: const Text('Back to sign in'),
                ),
              ],
              const SizedBox(height: 26),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    LucideIcons.shieldCheck,
                    color: scheme.primary,
                    size: 17,
                  ),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      'Secure workspace access',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                ],
              ),
              if (demo) ...[
                const SizedBox(height: 24),
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: scheme.primary.withValues(alpha: .06),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'FRONTEND DEMO',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 1.2,
                          color: scheme.primary,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        verify
                            ? 'Verification code: ${DemoRepository.demoCode}'
                            : 'Use the demo account. Do not enter real credentials.',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      if (!verify && !reset && !register)
                        Align(
                          alignment: Alignment.centerLeft,
                          child: TextButton(
                            key: const Key('fill-demo'),
                            style: TextButton.styleFrom(
                              padding: EdgeInsets.zero,
                            ),
                            onPressed: () {
                              _email.text = DemoRepository.demoEmail;
                              _password.text = DemoRepository.demoPassword;
                            },
                            child: const Text('Fill demo account'),
                          ),
                        ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 22),
              Text(
                'Developed by ${AppInfo.developer}',
                key: const Key('login-developer-credit'),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    );

    return Scaffold(
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            if (constraints.maxWidth < 860) {
              return SingleChildScrollView(
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(25, 24, 25, 36),
                    child: form,
                  ),
                ),
              );
            }
            return Row(
              children: [
                Expanded(
                  flex: 5,
                  child: Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: [
                          scheme.primary.withValues(alpha: .12),
                          const Color(0xFFDCF5E9),
                          const Color(0xFFE2F4F8),
                        ],
                      ),
                    ),
                    child: Stack(
                      children: [
                        const Positioned(
                          top: 42,
                          left: 42,
                          child: BrandMark(wordmark: true, size: 40),
                        ),
                        Center(
                          child: SingleChildScrollView(
                            child: Padding(
                              padding: const EdgeInsets.all(40),
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Center(
                                    child: BrandIllustration(height: 240),
                                  ),
                                  const SizedBox(height: 36),
                                  Text(
                                    'Your operations.\nOne connected workspace.',
                                    style: Theme.of(context)
                                        .textTheme
                                        .headlineLarge
                                        ?.copyWith(color: Brand.ink),
                                  ),
                                  const SizedBox(height: 16),
                                  const Text(
                                    'Workflows, reports and decisions,\nwith you in control.',
                                    style: TextStyle(
                                      fontSize: 16,
                                      color: Color(0xFF48655A),
                                      height: 1.7,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                        const Positioned(
                          bottom: 36,
                          left: 42,
                          child: Text(
                            'ULTRON · Ecom Manager',
                            style: TextStyle(color: Color(0xFF48655A)),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                Expanded(
                  flex: 6,
                  child: SingleChildScrollView(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 48,
                        vertical: 42,
                      ),
                      child: Center(child: form),
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
