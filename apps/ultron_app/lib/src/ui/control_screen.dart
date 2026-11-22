import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

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
    _tier = s.tier;
    final all = s.providers.isEmpty
        ? providerLabels.keys.toList()
        : s.providers;
    _order = [...s.order, ...all.where((p) => !s.order.contains(p))];
    _off = all.where((p) => !s.order.contains(p)).toSet();
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
                  Text('Model', style: theme.textTheme.titleMedium),
                  const SizedBox(height: 6),
                  Text(
                    'Auto picks the newest strong model of every provider that has a key, and moves to the next one when a model fails or runs out of credit.',
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
                  if (!_auto)
                    TextField(
                      controller: _model,
                      enabled: canManage && !_saving,
                      decoration: const InputDecoration(
                        labelText: 'Model tried first',
                        hintText: 'anthropic:claude-sonnet-5-5',
                      ),
                    ),
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
