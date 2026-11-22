import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:material_ui/material_ui.dart';

import '../domain/access.dart';
import '../domain/models.dart';
import '../state/providers.dart';
import 'components.dart';

/// Home: what needs attention, from the live services only. A number that could not be read says so;
/// it is never shown as 0.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});
  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _Read<T> {
  const _Read({this.value, this.error});
  final T? value;
  final String? error;
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  _Read<List<AppUser>>? _users;
  _Read<List<SmsPhone>>? _phones;
  _Read<AgentSettings>? _settings;
  _Read<AgentMemory>? _memory;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<_Read<T>> _read<T>(Future<T> Function() call) async {
    try {
      return _Read(value: await call());
    } on FrontendException catch (e) {
      return _Read(error: e.message);
    } catch (_) {
      return const _Read(error: 'Not available right now.');
    }
  }

  Future<void> _load() async {
    final repo = ref.read(repositoryProvider);
    final user = ref.read(authProvider).user;
    setState(() => _loading = true);
    final results = await Future.wait([
      if (user?.allows('users.manage') ?? false)
        _read(() async => (await repo.listUsers()).users)
      else
        Future.value(null),
      if (user?.allows('phone.manage') ?? false)
        _read(repo.smsPhones)
      else
        Future.value(null),
      if (user?.allows('agent.tools.read') ?? false)
        _read(repo.agentSettings)
      else
        Future.value(null),
      if (user?.allows('agent.tools.read') ?? false)
        _read(repo.agentMemory)
      else
        Future.value(null),
    ]);
    if (!mounted) return;
    setState(() {
      _users = results[0] as _Read<List<AppUser>>?;
      _phones = results[1] as _Read<List<SmsPhone>>?;
      _settings = results[2] as _Read<AgentSettings>?;
      _memory = results[3] as _Read<AgentMemory>?;
      _loading = false;
    });
  }

  String _ago(DateTime t) {
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 1) return 'just now';
    if (d.inHours < 1) return '${d.inMinutes} min ago';
    if (d.inDays < 1) return '${d.inHours} h ago';
    return '${d.inDays} days ago';
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authProvider).user;
    final width = MediaQuery.sizeOf(context).width;
    final columns = width >= 1100 ? 3 : (width >= 640 ? 2 : 1);
    final cards = <Widget>[
      if (_users != null)
        _users!.value == null
            ? StatCard(
                icon: LucideIcons.userPlus,
                label: 'Waiting for approval',
                value: '—',
                note: _users!.error,
              )
            : StatCard(
                icon: LucideIcons.userPlus,
                label: 'Waiting for approval',
                value:
                    '${_users!.value!.where((u) => u.status == 'pending').length}',
                note: 'New registrations (latest 50)',
                onTap: () => context.go('/app/admin'),
              ),
      if (_phones != null)
        _phones!.value == null
            ? StatCard(
                icon: LucideIcons.smartphone,
                label: 'SMS phones',
                value: '—',
                note: _phones!.error,
              )
            : StatCard(
                icon: LucideIcons.smartphone,
                label: 'SMS phones',
                value: '${_phones!.value!.where((p) => !p.blocked).length}',
                note: _phones!.value!.isEmpty
                    ? 'None yet: a phone joins with SMS only'
                    : 'Last SMS ${_ago(_phones!.value!.first.lastSeen)} · ${_phones!.value!.fold<int>(0, (a, p) => a + p.sent)} sent',
                onTap: () => context.go('/app/control'),
              ),
      if (_settings != null)
        _settings!.value == null
            ? StatCard(
                icon: LucideIcons.brain,
                label: 'Agent model',
                value: '—',
                note: _settings!.error,
              )
            : StatCard(
                icon: LucideIcons.brain,
                label: 'Agent model',
                value: _settings!.value!.auto
                    ? 'Auto'
                    : _settings!.value!.model.split(':').last,
                note:
                    '${_settings!.value!.tier == 'fast' ? 'Fast & cheap' : 'Smart'} · ${_settings!.value!.order.length} providers in order',
                onTap: () => context.go('/app/control'),
              ),
      if (_memory != null)
        _memory!.value == null
            ? StatCard(
                icon: LucideIcons.bookOpen,
                label: 'Agent memory',
                value: '—',
                note: _memory!.error,
              )
            : StatCard(
                icon: LucideIcons.bookOpen,
                label: 'Agent memory',
                value:
                    '${_memory!.value!.counts.values.fold<int>(0, (a, b) => a + b)}',
                note:
                    'Notes · ${_memory!.value!.counts['incident'] ?? 0} incidents',
                onTap: () => context.go('/app/control'),
              ),
    ];
    return RefreshIndicator(
      onRefresh: _load,
      child: PageBody(
        children: [
          EmeraldPanel(
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Hello, ${user?.name.split(' ').first ?? ''}',
                        style: const TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        '${user?.roleName ?? ''} · what needs your attention today',
                        style: const TextStyle(
                          fontSize: 14,
                          color: Color(0xFFE6F6EE),
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Refresh',
                  onPressed: _loading ? null : _load,
                  icon: const Icon(
                    LucideIcons.refreshCw,
                    size: 20,
                    color: Colors.white,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          if (_loading && cards.isEmpty)
            const Padding(
              padding: EdgeInsets.all(40),
              child: Center(
                child: CircularProgressIndicator(semanticsLabel: 'Loading'),
              ),
            )
          else if (cards.isEmpty)
            const NotePanel(
              'Your role has no overview yet. Ask an administrator for more access.',
            )
          else
            LayoutBuilder(
              builder: (context, box) {
                const gap = 12.0;
                final w = (box.maxWidth - gap * (columns - 1)) / columns;
                return Wrap(
                  spacing: gap,
                  children: [
                    for (final c in cards) SizedBox(width: w, child: c),
                  ],
                );
              },
            ),
        ],
      ),
    );
  }
}
