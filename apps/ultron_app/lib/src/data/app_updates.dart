import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

import '../app_info.dart';
import '../state/providers.dart';

class AppRelease {
  const AppRelease({
    required this.version,
    required this.build,
    required this.url,
    required this.sha256,
    required this.size,
  });
  final String version, sha256;
  final int build, size;
  final Uri url;

  static AppRelease parse(Map<String, dynamic> data, Uri origin) {
    final url = Uri.parse(data['url'] as String);
    final build = data['build'] as int;
    final size = data['size'] as int;
    final sha = data['sha256'] as String;
    if (url.origin != origin.origin ||
        url.scheme != 'https' ||
        url.userInfo.isNotEmpty ||
        !url.path.startsWith('/api/releases/files/releases/') ||
        url.hasQuery ||
        url.hasFragment ||
        build < 1 ||
        size < 1 ||
        !RegExp(r'^[a-f0-9]{64}$').hasMatch(sha)) {
      throw const FormatException('Invalid release');
    }
    return AppRelease(
      version: data['version'] as String,
      build: build,
      url: url,
      sha256: sha,
      size: size,
    );
  }
}

class UpdateState {
  const UpdateState({this.release, this.busy = false, this.message});
  final AppRelease? release;
  final bool busy;
  final String? message;
}

final updatesProvider = NotifierProvider<UpdatesController, UpdateState>(
  UpdatesController.new,
);

class UpdatesController extends Notifier<UpdateState> {
  static const _channel = MethodChannel('ultron/updates');
  @override
  UpdateState build() => const UpdateState();

  String? get platform => kIsWeb
      ? null
      : switch (defaultTargetPlatform) {
          TargetPlatform.android => 'android',
          TargetPlatform.windows => 'windows',
          TargetPlatform.macOS => 'macos',
          TargetPlatform.linux => 'linux',
          _ => null,
        };

  Future<void> check() async {
    if (state.busy) return;
    if (platform == null) {
      state = const UpdateState(
        message: 'Updates for this platform are not available here.',
      );
      return;
    }
    state = UpdateState(release: state.release, busy: true);
    try {
      final origin = Uri.parse(appApiUrl);
      final response = await http
          .get(origin.resolve('/api/releases/latest?platform=$platform'))
          .timeout(const Duration(seconds: 20));
      if (!ref.mounted) return;
      if (response.statusCode != 200) {
        throw const FormatException('Unavailable');
      }
      final release = AppRelease.parse(
        jsonDecode(response.body) as Map<String, dynamic>,
        origin,
      );
      state = release.build > AppInfo.build
          ? UpdateState(
              release: release,
              message: 'ULTRON ${release.version} is ready.',
            )
          : const UpdateState(message: 'You have the latest version.');
    } catch (_) {
      if (ref.mounted) {
        state = UpdateState(
          release: state.release,
          message: 'Could not check for updates. Try again later.',
        );
      }
    }
  }

  Future<void> install() async {
    final release = state.release;
    if (release == null || state.busy) return;
    state = UpdateState(
      release: release,
      busy: true,
      message: 'Downloading update…',
    );
    try {
      String message;
      if (platform == 'android') {
        final result = await _channel.invokeMethod<String>('install', {
          'url': release.url.toString(),
          'sha256': release.sha256,
          'size': release.size,
          'build': release.build,
        });
        message = result == 'permission'
            ? 'Allow ULTRON to install updates, return here and tap Update again.'
            : 'Confirm the update in Android’s installer.';
      } else {
        final opened = await launchUrl(
          release.url,
          mode: LaunchMode.externalApplication,
        );
        if (!opened) throw const FormatException('Download unavailable');
        message = 'Open the downloaded package to update ULTRON.';
      }
      if (ref.mounted) state = UpdateState(release: release, message: message);
    } on PlatformException catch (e) {
      if (ref.mounted) {
        state = UpdateState(
          release: release,
          message: e.message ?? 'Update could not finish. Try again.',
        );
      }
    } catch (_) {
      if (ref.mounted) {
        state = UpdateState(
          release: release,
          message: 'Update could not finish. Try again.',
        );
      }
    }
  }
}
