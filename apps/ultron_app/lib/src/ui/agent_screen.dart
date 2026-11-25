import 'dart:async';
import 'dart:typed_data';

import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:url_launcher/url_launcher.dart';

import '../domain/models.dart';
import '../state/providers.dart';
import 'components.dart';

class AgentScreen extends ConsumerStatefulWidget {
  const AgentScreen({super.key});
  @override
  ConsumerState<AgentScreen> createState() => _AgentScreenState();
}

class _AgentScreenState extends ConsumerState<AgentScreen> {
  final _message = TextEditingController();
  bool _busy = false;
  bool _refreshing = false;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _poll = Timer.periodic(const Duration(seconds: 5), (_) async {
      if (_busy ||
          _refreshing ||
          !(ref
                  .read(workspaceProvider)
                  .asData
                  ?.value
                  .messages
                  .any((m) => m.pending) ??
              false)) {
        return;
      }
      _refreshing = true;
      try {
        await ref.read(workspaceProvider.notifier).refresh();
      } catch (_) {
        // A temporary network failure keeps the conversation and retries on the next tick.
      } finally {
        _refreshing = false;
      }
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    _message.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final text = _message.text.trim();
    if (text.isEmpty || _busy) return;
    setState(() => _busy = true);
    try {
      await ref.read(workspaceProvider.notifier).sendMessage(text);
      if (mounted) _message.clear();
    } on FrontendException catch (error) {
      if (mounted) showNotice(context, error.message);
    } catch (_) {
      if (mounted) {
        showNotice(context, 'The message could not be sent. Try again.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => DataGate(
    builder: (data) => Column(
      children: [
        Expanded(
          child: SingleChildScrollView(
            reverse: true,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 780),
                child: Padding(
                  padding: const EdgeInsets.all(22),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const PageHeading(
                        'ULTRON',
                        subtitle: 'Operations assistant · Live',
                      ),
                      for (final message in data.messages)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 22),
                          child: _MessageBubble(message: message),
                        ),
                      OutlinedButton.icon(
                        onPressed: () => context.go('/app/connections'),
                        icon: const Icon(LucideIcons.externalLink, size: 17),
                        label: const Text('Review connections'),
                      ),
                      const SizedBox(height: 18),
                      Row(
                        children: [
                          const Expanded(child: Divider()),
                          Flexible(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 14,
                              ),
                              child: Text(
                                'Changes need your approval',
                                textAlign: TextAlign.center,
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            ),
                          ),
                          const Expanded(child: Divider()),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
        SafeArea(
          top: false,
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 780),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 10, 20, 18),
                child: Container(
                  padding: const EdgeInsets.fromLTRB(14, 5, 6, 5),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.surfaceContainerLowest,
                    border: Border.all(
                      color: Theme.of(context).colorScheme.outlineVariant,
                    ),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Expanded(
                        child: TextField(
                          key: const Key('agent-message'),
                          controller: _message,
                          maxLength: 2000,
                          minLines: 1,
                          maxLines: 5,
                          decoration: const InputDecoration(
                            hintText: 'Ask Ultron…',
                            counterText: '',
                            filled: false,
                            border: InputBorder.none,
                            enabledBorder: InputBorder.none,
                            focusedBorder: InputBorder.none,
                            contentPadding: EdgeInsets.symmetric(vertical: 13),
                          ),
                          onSubmitted: (_) => _send(),
                        ),
                      ),
                      IconButton.filled(
                        key: const Key('agent-send'),
                        tooltip: 'Send message',
                        onPressed: _busy ? null : _send,
                        icon: _busy
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(LucideIcons.arrowUp, size: 20),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    ),
  );
}

/// A file of an agent answer: a picture is shown, any file opens (downloads) with a tap.
class _FileCard extends ConsumerStatefulWidget {
  const _FileCard({required this.file});
  final AgentFile file;
  @override
  ConsumerState<_FileCard> createState() => _FileCardState();
}

class _FileCardState extends ConsumerState<_FileCard> {
  Future<Uint8List>? _picture;
  bool _opening = false;

  @override
  void initState() {
    super.initState();
    if (widget.file.isImage) {
      _picture = ref.read(repositoryProvider).chatFileBytes(widget.file.id);
    }
  }

  Future<void> _open() async {
    if (_opening) return;
    setState(() => _opening = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final link = await ref
          .read(repositoryProvider)
          .chatFileLink(widget.file.id);
      final opened = await launchUrl(
        link,
        mode: LaunchMode.externalApplication,
      );
      if (!opened) throw const FormatException();
    } catch (_) {
      messenger.showSnackBar(
        const SnackBar(
          content: Text('The file could not be opened. Try again.'),
        ),
      );
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final file = widget.file;
    final kb = (file.size / 1024).ceil();
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: _open,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_picture != null)
              FutureBuilder<Uint8List>(
                future: _picture,
                builder: (context, snap) => snap.hasData
                    ? Image.memory(snap.data!, fit: BoxFit.contain)
                    : SizedBox(
                        height: 120,
                        child: Center(
                          child: snap.hasError
                              ? const Text('Picture unavailable')
                              : const CircularProgressIndicator(),
                        ),
                      ),
              ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  Icon(
                    file.isImage ? LucideIcons.image : LucideIcons.fileText,
                    size: 18,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          file.name,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        if (file.caption.isNotEmpty)
                          Text(
                            file.caption,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                      ],
                    ),
                  ),
                  Text('$kb KB', style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(width: 8),
                  _opening
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(LucideIcons.download, size: 18),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});
  final AgentMessage message;
  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Align(
      alignment: message.fromOwner
          ? Alignment.centerRight
          : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 570),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!message.fromOwner)
              const Padding(
                padding: EdgeInsets.only(bottom: 9),
                child: BrandMark(size: 24, wordmark: true),
              ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 17, vertical: 14),
              decoration: BoxDecoration(
                color: scheme.primary.withValues(
                  alpha: message.fromOwner ? .10 : .035,
                ),
                borderRadius: BorderRadius.circular(17),
              ),
              child: SelectableText(
                message.text,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
            for (final file in message.files) ...[
              const SizedBox(height: 10),
              _FileCard(file: file),
            ],
            if (message.sources.isNotEmpty) ...[
              const SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(15),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Sources',
                        style: TextStyle(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 9),
                      for (final source in message.sources)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 6),
                          child: Row(
                            children: [
                              const Icon(LucideIcons.fileText, size: 16),
                              const SizedBox(width: 10),
                              Expanded(
                                child: Text(
                                  source,
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
