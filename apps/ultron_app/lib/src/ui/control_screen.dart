import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../data/agent_bridge.dart';
import '../domain/access.dart';
import '../domain/models.dart';
import '../state/providers.dart';
import 'components.dart';

/// The agent's control panel: which models it uses (auto-select, tier, provider order) and what it
/// remembers. Saved settings reach the agent within 5 minutes.
class ControlScreen extends ConsumerStatefulWidget {
  const ControlScreen({super.key});
  @override
  ConsumerState<ControlScreen> createState() => _ControlScreenState();
}

class _ControlScreenState extends ConsumerState<ControlScreen> {
  final _search = TextEditingController();
  final _model = TextEditingController();
  AgentSettings? _settings;
  AgentMemory? _memory;
  List<SmsPhone>? _phones;
  List<PhoneAgent>? _agents;
  List<ApiKey> _keys = [];
  Map<String, List<String>> _models = {};
  String _pickProvider = 'anthropic';
  String? _pickModel;
  AgentStatus? _agent;
  bool _agentBusy = false;
  static const _bridge = AgentBridge();
  String? _phonesError;
  String _tier = 'smart', _kind = '';
  bool _auto = true, _loading = true, _saving = false;
  List<String> _order = [];
  Set<String> _off = {};
  String? _error, _saved;
  int _request = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    _model.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final request = ++_request;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repository = ref.read(repositoryProvider);
      final settings = await repository.agentSettings();
      final memory = await repository.agentMemory(
        kind: _kind,
        search: _search.text.trim(),
      );
      if (!mounted || request != _request) return;
      setState(() {
        _settings = settings;
        _memory = memory;
        _apply(settings);
      });
      await _loadBrain();
      await _loadPhones();
    } on FrontendException catch (e) {
      if (mounted && request == _request) setState(() => _error = e.message);
    } catch (_) {
      if (mounted && request == _request) {
        setState(() => _error = 'The control panel is unavailable. Try again.');
      }
    } finally {
      if (mounted && request == _request) setState(() => _loading = false);
    }
  }

  void _apply(AgentSettings s) {
    _auto = s.auto;
    _model.text = s.auto ? '' : s.model;
    if (!s.auto && s.model.contains(':')) {
      _pickProvider = s.model.substring(0, s.model.indexOf(':'));
      _pickModel = s.model.substring(s.model.indexOf(':') + 1);
    }
    _tier = s.tier;
    final all = s.providers.isEmpty
        ? providerLabels.keys.toList()
        : s.providers;
    _order = [...s.order, ...all.where((p) => !s.order.contains(p))];
    _off = all.where((p) => !s.order.contains(p)).toSet();
  }

  /// The API keys and the models the agent last read; neither failing hides the rest of the page.
  Future<void> _loadBrain() async {
    final repo = ref.read(repositoryProvider);
    try {
      final keys = await repo.apiKeys();
      final models = await repo.agentModels();
      if (mounted) {
        setState(() {
          _keys = keys;
          _models = models;
        });
      }
    } on FrontendException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  bool _refreshing = false;

  /// Every provider's list read again with its key: a new model appears, a retired one goes.
  Future<void> _refreshModels() async {
    setState(() => _refreshing = true);
    try {
      final models = await ref.read(repositoryProvider).refreshModels();
      if (mounted) setState(() => _models = models);
    } on FrontendException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _refreshing = false);
    }
  }

  /// The provider's models with a search box.
  Future<void> _searchModel() async {
    final all = _modelsOf(_pickProvider);
    final picked = await showDialog<String>(
      context: context,
      builder: (context) => _ModelSearch(models: all, selected: _pickModel),
    );
    if (picked != null && mounted) {
      setState(() {
        _auto = false;
        _pickModel = picked;
        _model.text = '$_pickProvider:$picked';
      });
    }
  }

  List<String> _modelsOf(String provider) {
    final read = _models[provider] ?? const [];
    return read.isNotEmpty ? read : (knownModels[provider] ?? const []);
  }

  Future<void> _keysDo(Future<List<ApiKey>> Function() action) async {
    try {
      final keys = await action();
      // a key added or removed changes which models can be listed: the app API read them with the key
      final models = await ref
          .read(repositoryProvider)
          .agentModels()
          .catchError((_) => _models);
      if (mounted) {
        setState(() {
          _keys = keys;
          _models = models;
        });
      }
    } on FrontendException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _addKey() async {
    var provider = 'anthropic', hidden = true;
    final label = TextEditingController(), key = TextEditingController();
    final added = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, set) => AlertDialog(
          title: const Text('Add API key'),
          content: SizedBox(
            width: 440,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                DropdownButtonFormField<String>(
                  initialValue: provider,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Provider'),
                  items: [
                    for (final p in providerLabels.keys.where(
                      (p) => p != 'cloudflare',
                    ))
                      DropdownMenuItem(
                        value: p,
                        child: Text(providerLabels[p]!),
                      ),
                  ],
                  onChanged: (v) => set(() => provider = v!),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: label,
                  decoration: const InputDecoration(
                    labelText: 'Name (optional)',
                    hintText: 'e.g. Free key 2',
                  ),
                ),
                const SizedBox(height: 14),
                TextField(
                  key: const Key('api-key-field'),
                  controller: key,
                  obscureText: hidden,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: InputDecoration(
                    labelText: 'API key',
                    helperText: 'Stored encrypted; the app only ever shows its last 4 characters',
                    suffixIcon: IconButton(
                      tooltip: hidden ? 'Show key' : 'Hide key',
                      onPressed: () => set(() => hidden = !hidden),
                      icon: Icon(
                        hidden ? LucideIcons.eye : LucideIcons.eyeOff,
                        size: 18,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(c),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(c, true),
              child: const Text('Add key'),
            ),
          ],
        ),
      ),
    );
    if (added == true && mounted) {
      await _keysDo(
        () => ref
            .read(repositoryProvider)
            .addApiKey(provider: provider, key: key.text, label: label.text),
      );
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
    label.dispose();
    key.dispose();
  }

  Widget _keyTile(ApiKey k, bool canManage) {
    final repo = ref.read(repositoryProvider);
    final (String word, Tone tone) = k.status == 'bad'
        ? ('Refused', Tone.bad)
        : k.resting
        ? (
            'Limit · back ${k.restingUntil!.toLocal().toString().substring(11, 16)}',
            Tone.warn,
          )
        : ('Ready', Tone.good);
    return Card(
      child: ListTile(
        leading: const Icon(LucideIcons.keyRound),
        title: Text(
          '${k.label.isEmpty ? providerLabels[k.provider] ?? k.provider : k.label}  ••••${k.last4}',
        ),
        subtitle: Align(
          alignment: Alignment.centerLeft,
          child: StatusPill(word, tone: tone),
        ),
        trailing: canManage
            ? PopupMenuButton<String>(
                tooltip: 'Key actions',
                onSelected: (a) => _keysDo(
                  () => switch (a) {
                    'up' => repo.changeApiKey(k.id, move: 'up'),
                    'down' => repo.changeApiKey(k.id, move: 'down'),
                    'retry' => repo.changeApiKey(k.id, reset: true),
                    _ => repo.removeApiKey(k.id),
                  },
                ),
                itemBuilder: (_) => [
                  const PopupMenuItem(value: 'up', child: Text('Try earlier')),
                  const PopupMenuItem(value: 'down', child: Text('Try later')),
                  if (k.status != 'ok')
                    const PopupMenuItem(
                      value: 'retry',
                      child: Text('Try again now'),
                    ),
                  const PopupMenuItem(value: 'remove', child: Text('Remove')),
                ],
              )
            : null,
      ),
    );
  }

  Future<void> _loadPhones() async {
    if (!(ref.read(authProvider).user?.allows('phone.manage') ?? false)) return;
    try {
      final agents = await ref.read(repositoryProvider).phoneAgents();
      final agent = _bridge.supported ? await _bridge.status() : null;
      if (mounted) {
        setState(() {
          _agents = agents;
          _agent = agent;
        });
      }
    } on FrontendException catch (e) {
      if (mounted) setState(() => _phonesError = e.message);
    } on PlatformException catch (_) {
      /* the Android side refused: the list still shows */
    } on MissingPluginException catch (_) {
      /* a build without the Android side (tests, other platforms): the list still shows */
    }
    try {
      final phones = await ref.read(repositoryProvider).smsPhones();
      if (mounted) {
        setState(() {
          _phones = phones;
          _phonesError = null;
        });
      }
    } on FrontendException catch (e) {
      if (mounted) setState(() => _phonesError = e.message);
    }
  }

  /// Agent mode on this phone: a token from the app API for it, handed to the Android service.
  Future<void> _agentOn(bool on) async {
    setState(() => _agentBusy = true);
    try {
      if (on) {
        final token = await ref
            .read(repositoryProvider)
            .newPhoneAgent(_agent?.device ?? 'Android phone');
        final status = await _bridge.start(token);
        final agents = await ref.read(repositoryProvider).phoneAgents();
        if (mounted) {
          setState(() {
            _agent = status;
            _agents = agents;
          });
        }
      } else {
        final status = await _bridge.stop();
        if (mounted) setState(() => _agent = status);
      }
    } on FrontendException catch (e) {
      if (mounted) setState(() => _phonesError = e.message);
    } on PlatformException catch (e) {
      if (mounted) {
        setState(
          () => _phonesError = e.message ?? 'Agent mode could not change.',
        );
      }
    } finally {
      if (mounted) setState(() => _agentBusy = false);
    }
  }

  Future<void> _revoke(PhoneAgent a) async {
    try {
      final agents = await ref.read(repositoryProvider).revokePhoneAgent(a.id);
      if (mounted) setState(() => _agents = agents);
    } on FrontendException catch (e) {
      if (mounted) setState(() => _phonesError = e.message);
    }
  }

  Future<void> _block(SmsPhone phone, bool blocked) async {
    try {
      final phones = await ref
          .read(repositoryProvider)
          .blockPhone(phone, blocked: blocked);
      if (mounted) setState(() => _phones = phones);
    } on FrontendException catch (e) {
      if (mounted) setState(() => _phonesError = e.message);
    }
  }

  Future<void> _reloadMemory() async {
    try {
      final memory = await ref
          .read(repositoryProvider)
          .agentMemory(kind: _kind, search: _search.text.trim());
      if (mounted) setState(() => _memory = memory);
    } on FrontendException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _save() async {
    final settings = _settings;
    if (settings == null) return;
    final model = _auto ? 'auto' : _model.text.trim();
    final order = _order.where((p) => !_off.contains(p)).toList();
    if (!_auto && !RegExp(r'^[a-z]+:\S{1,120}$').hasMatch(model)) {
      setState(
        () => _error = 'Write the model as provider:model, for example anthropic:claude-sonnet-5-5.',
      );
      return;
    }
    if (order.isEmpty) {
      setState(() => _error = 'Keep at least one provider on.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
      _saved = null;
    });
    try {
      final saved = await ref
          .read(repositoryProvider)
          .saveAgentSettings(
            model: model,
            tier: _tier,
            order: order,
            revision: settings.revision,
          );
      if (mounted) {
        setState(() {
          _settings = saved;
          _apply(saved);
          _saved = 'Saved. The agent uses it within 5 minutes.';
        });
      }
    } on FrontendException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'The settings could not be saved.');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _forget(AgentNote note) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Remove this note?'),
        content: Text(note.text),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c),
            child: const Text('Keep'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(c, true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (sure != true || !mounted) return;
    try {
      await ref.read(repositoryProvider).forgetNote(note.id);
      await _reloadMemory();
    } on FrontendException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final canManage = canAccess(ref, 'agent.manage'),
        canForget = canAccess(ref, 'memory.manage');
    final theme = Theme.of(context);
    return PageBody(
      maxWidth: 1060,
      children: [
        PageHeading(
          'Agent control panel',
          subtitle:
              'Choose the models the agent uses and review what it remembers.',
        ),
        Row(
          children: [
            const Spacer(),
            IconButton(
              onPressed: _loading ? null : _load,
              tooltip: 'Refresh',
              icon: const Icon(LucideIcons.refreshCw, size: 19),
            ),
          ],
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 14),
            child: NotePanel(_error!, warning: true),
          ),
        if (_loading && _settings == null)
          const Center(
            child: Padding(
              padding: EdgeInsets.all(32),
              child: CircularProgressIndicator(),
            ),
          )
        else if (_settings != null) ...[
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('Brain: model', style: theme.textTheme.titleMedium),
                  const SizedBox(height: 6),
                  Text(
                    'Choose a provider and model below, or use Auto. Choosing a model turns Auto off; save to apply. If it fails, the agent tries your other providers.',
                    style: theme.textTheme.bodySmall,
                  ),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    value: _auto,
                    onChanged: canManage && !_saving
                        ? (v) => setState(() => _auto = v)
                        : null,
                    title: const Text('Auto-select the model'),
                  ),
                  ...[
                    DropdownButtonFormField<String>(
                      key: const Key('pick-provider'),
                      initialValue: _pickProvider,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'Provider'),
                      items: [
                        for (final p in providerLabels.keys)
                          DropdownMenuItem(
                            value: p,
                            child: Text(
                              providerLabels[p]!,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                      ],
                      onChanged: canManage && !_saving
                          ? (v) => setState(() {
                              _auto = false;
                              _pickProvider = v!;
                              _pickModel = _modelsOf(v).firstOrNull;
                              _model.text =
                                  '$_pickProvider:${_pickModel ?? ''}';
                            })
                          : null,
                    ),
                    const SizedBox(height: 12),
                    InkWell(
                      key: ValueKey('pick-model-$_pickProvider'),
                      borderRadius: BorderRadius.circular(12),
                      onTap: canManage && !_saving ? _searchModel : null,
                      child: InputDecorator(
                        decoration: InputDecoration(
                          labelText: 'Model',
                          suffixIcon: const Icon(LucideIcons.search, size: 18),
                          helperText:
                              (_models[_pickProvider] ?? const []).isEmpty
                              ? 'Known models; add a key for this provider to load its full list'
                              : '${_models[_pickProvider]!.length} models this provider offers',
                        ),
                        child: Text(
                          _modelsOf(_pickProvider).contains(_pickModel)
                              ? _pickModel!
                              : 'Choose a model',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                    Align(
                      alignment: Alignment.centerRight,
                      child: TextButton.icon(
                        key: const Key('refresh-models'),
                        onPressed: canManage && !_refreshing
                            ? _refreshModels
                            : null,
                        icon: _refreshing
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(LucideIcons.refreshCw, size: 15),
                        label: const Text('Refresh models'),
                      ),
                    ),
                  ],
                  const SizedBox(height: 16),
                  SegmentedButton<String>(
                    segments: const [
                      ButtonSegment(
                        value: 'smart',
                        label: Text('Smart'),
                        icon: Icon(LucideIcons.brain, size: 16),
                      ),
                      ButtonSegment(
                        value: 'fast',
                        label: Text('Fast & cheap'),
                        icon: Icon(LucideIcons.zap, size: 16),
                      ),
                    ],
                    selected: {_tier},
                    onSelectionChanged: canManage && !_saving
                        ? (v) => setState(() => _tier = v.first)
                        : null,
                  ),
                  const SizedBox(height: 18),
                  Text(
                    'Providers, in the order they are tried',
                    style: theme.textTheme.titleSmall,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'A provider is used only when its key is set for the agent. Drag to reorder; switch off to skip it.',
                    style: theme.textTheme.bodySmall,
                  ),
                  ReorderableListView(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    buildDefaultDragHandles: canManage,
                    onReorderItem: (from, to) => setState(
                      () => _order.insert(to, _order.removeAt(from)),
                    ),
                    children: [
                      for (final p in _order)
                        ListTile(
                          key: ValueKey(p),
                          contentPadding: EdgeInsets.zero,
                          leading: Icon(
                            canManage
                                ? LucideIcons.gripVertical
                                : LucideIcons.cpu,
                            size: 18,
                          ),
                          title: Text(providerLabels[p] ?? p),
                          trailing: Switch(
                            value: !_off.contains(p),
                            onChanged: canManage && !_saving
                                ? (on) => setState(
                                    () => on ? _off.remove(p) : _off.add(p),
                                  )
                                : null,
                          ),
                        ),
                    ],
                  ),
                  if (_saved != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        _saved!,
                        style: TextStyle(color: theme.colorScheme.primary),
                      ),
                    ),
                  if (canManage)
                    Align(
                      alignment: Alignment.centerRight,
                      child: Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: FilledButton.icon(
                          onPressed: _saving ? null : _save,
                          icon: const Icon(LucideIcons.save, size: 17),
                          label: Text(
                            _saving ? 'Saving…' : 'Save model settings',
                          ),
                        ),
                      ),
                    )
                  else
                    const NotePanel(
                      'Only an administrator can change the model settings.',
                    ),
                ],
              ),
            ),
          ),
          SectionHeading(
            'Brain: API keys',
            trailing: canAccess(ref, 'agent.manage')
                ? FilledButton.tonalIcon(
                    key: const Key('add-key'),
                    onPressed: _addKey,
                    icon: const Icon(LucideIcons.plus, size: 18),
                    label: const Text('Add key'),
                  )
                : null,
          ),
          Text(
            'Add as many keys as you like for each provider. The agent uses them in order; when a key hits its '
            'limit it moves to the next key at once, then to the next provider. Free: Groq, Google AI Studio, '
            'NVIDIA; Cloudflare Workers AI needs no key.',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          if (_keys.isEmpty)
            const NotePanel(
              'No key added here yet. The agent uses the keys set on GitHub, and Cloudflare Workers AI.',
            )
          else
            for (final p in providerLabels.keys)
              if (_keys.any((k) => k.provider == p)) ...[
                Padding(
                  padding: const EdgeInsets.only(top: 6, bottom: 6),
                  child: Text(
                    providerLabels[p]!,
                    style: theme.textTheme.titleSmall,
                  ),
                ),
                for (final k in _keys.where((k) => k.provider == p))
                  _keyTile(k, canAccess(ref, 'agent.manage')),
              ],
          if (canAccess(ref, 'phone.manage')) ...[
            const SectionHeading('SMS phones'),
            Text(
              'Phones in SMS only mode. Each SMS goes to the sheet with the phone\'s name. Block one to stop taking its SMS.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            if (_phonesError != null)
              NotePanel(_phonesError!, warning: true)
            else if (_phones == null)
              const SizedBox.shrink()
            else if (_phones!.isEmpty)
              const NotePanel(
                'No phone yet. On a phone, open ULTRON and choose "SMS only".',
              )
            else
              for (final ph in _phones!)
                Card(
                  child: ListTile(
                    leading: Icon(
                      ph.blocked
                          ? LucideIcons.smartphoneNfc
                          : LucideIcons.smartphone,
                    ),
                    title: Text(ph.name),
                    subtitle: Text(
                      'Last SMS ${ph.lastSeen.toLocal().toString().substring(0, 16)} · ${ph.sent} sent',
                    ),
                    trailing: canAccess(ref, 'phone.manage')
                        ? TextButton(
                            onPressed: () => _block(ph, !ph.blocked),
                            child: Text(ph.blocked ? 'Unblock' : 'Block'),
                          )
                        : null,
                  ),
                ),
          ],
          if (canAccess(ref, 'phone.manage')) ...[
            const SectionHeading('Agent mode'),
            Text(
              'A phone that does work for the bots on its own line (the Myntra style lookups of zero TD, '
              'when the office PC is off). Turn it on from that phone; revoke a phone here.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            if (_bridge.supported && _agent != null)
              Card(
                child: SwitchListTile(
                  key: const Key('agent-switch'),
                  value: _agent!.on,
                  onChanged: _agentBusy ? null : _agentOn,
                  title: Text('This phone: ${_agent!.device}'),
                  subtitle: Text(
                    _agent!.on
                        ? (_agent!.lastPoll == null
                              ? 'On, waiting for the first check-in'
                              : 'On · checked in ${_agent!.lastPoll!.toLocal().toString().substring(11, 16)}'
                                    '${_agent!.lastJob.isEmpty ? '' : ' · ${_agent!.lastJob}'}')
                        : 'Off',
                  ),
                ),
              ),
            for (final a in _agents ?? const <PhoneAgent>[])
              if (!a.revoked)
                Card(
                  child: ListTile(
                    leading: const Icon(LucideIcons.bot),
                    title: Text(a.device),
                    subtitle: Text(
                      a.lastSeen == null
                          ? 'Not checked in yet'
                          : 'Last check-in ${a.lastSeen!.toLocal().toString().substring(0, 16)}',
                    ),
                    trailing: TextButton(
                      onPressed: () => _revoke(a),
                      child: const Text('Revoke'),
                    ),
                  ),
                ),
          ],
          const SizedBox(height: 22),
          Text('Memory', style: theme.textTheme.titleMedium),
          const SizedBox(height: 6),
          Text(
            'What the agent keeps between messages. It never stores passwords, OTPs, keys, phone numbers or emails.',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              ChoiceChip(
                label: Text(
                  'All (${_memory?.counts.values.fold<int>(0, (a, b) => a + b) ?? 0})',
                ),
                selected: _kind.isEmpty,
                onSelected: (_) {
                  setState(() => _kind = '');
                  _reloadMemory();
                },
              ),
              for (final k in noteKinds.entries)
                ChoiceChip(
                  label: Text('${k.value} (${_memory?.counts[k.key] ?? 0})'),
                  selected: _kind == k.key,
                  onSelected: (_) {
                    setState(() => _kind = k.key);
                    _reloadMemory();
                  },
                ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _search,
            onSubmitted: (_) => _reloadMemory(),
            decoration: InputDecoration(
              hintText: 'Search the notes',
              prefixIcon: const Icon(LucideIcons.search, size: 18),
              suffixIcon: IconButton(
                tooltip: 'Search',
                onPressed: _reloadMemory,
                icon: const Icon(LucideIcons.arrowRight, size: 18),
              ),
            ),
          ),
          const SizedBox(height: 12),
          if (_memory!.notes.isEmpty)
            const Padding(
              padding: EdgeInsets.all(25),
              child: Text('No notes match.'),
            ),
          for (final n in _memory!.notes)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(n.text),
                          const SizedBox(height: 8),
                          Wrap(
                            spacing: 6,
                            runSpacing: 6,
                            children: [
                              Chip(
                                label: Text(
                                  noteKinds[n.kind] ?? n.kind,
                                  style: const TextStyle(fontSize: 11),
                                ),
                              ),
                              for (final t in n.tags)
                                Chip(
                                  label: Text(
                                    t,
                                    style: const TextStyle(fontSize: 11),
                                  ),
                                ),
                            ],
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Updated ${n.updated.toLocal().toString().substring(0, 16)} · used ${n.uses} times${n.source.isEmpty ? '' : ' · from ${n.source}'}',
                            style: theme.textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                    if (canForget)
                      IconButton(
                        tooltip: 'Remove this note',
                        onPressed: () => _forget(n),
                        icon: const Icon(LucideIcons.trash2, size: 18),
                      ),
                  ],
                ),
              ),
            ),
        ],
      ],
    );
  }
}

/// A provider's models, filtered as the owner types.
class _ModelSearch extends StatefulWidget {
  const _ModelSearch({required this.models, this.selected});
  final List<String> models;
  final String? selected;
  @override
  State<_ModelSearch> createState() => _ModelSearchState();
}

class _ModelSearchState extends State<_ModelSearch> {
  String _query = '';
  @override
  Widget build(BuildContext context) {
    final words = _query
        .toLowerCase()
        .split(RegExp(r'\s+'))
        .where((w) => w.isNotEmpty);
    final shown = widget.models
        .where((m) => words.every(m.toLowerCase().contains))
        .toList();
    return AlertDialog(
      title: const Text('Choose a model'),
      contentPadding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
      content: SizedBox(
        width: 440,
        height: 420,
        child: Column(
          children: [
            TextField(
              key: const Key('model-search'),
              autofocus: true,
              decoration: const InputDecoration(
                hintText: 'Search models',
                prefixIcon: Icon(LucideIcons.search, size: 18),
              ),
              onChanged: (v) => setState(() => _query = v),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                '${shown.length} of ${widget.models.length}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            Expanded(
              child: shown.isEmpty
                  ? const Center(child: Text('No model matches.'))
                  : ListView.builder(
                      itemCount: shown.length,
                      itemBuilder: (context, i) => ListTile(
                        dense: true,
                        title: Text(shown[i], overflow: TextOverflow.ellipsis),
                        trailing: shown[i] == widget.selected
                            ? const Icon(LucideIcons.check, size: 16)
                            : null,
                        onTap: () => Navigator.pop(context, shown[i]),
                      ),
                    ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
      ],
    );
  }
}
