import 'package:flutter_test/flutter_test.dart';
import 'package:ultron_app/src/data/app_updates.dart';

void main() {
  final origin = Uri.parse('https://api.example.test');
  final data = <String, dynamic>{
    'version': '0.1.42',
    'build': 142,
    'size': 100,
    'sha256': 'a' * 64,
    'url': 'https://api.example.test/api/releases/files/releases/142/android/ULTRON.apk',
  };
  test('an update preserves its build number, digest and size', () {
    final release = AppRelease.parse(data, origin);
    expect(release.build, 142);
    expect(release.sha256, 'a' * 64);
    expect(release.size, 100);
  });
  test('foreign origins, invalid digests and invalid sizes are rejected', () {
    for (final change in [
      {
        'url': 'https://elsewhere.example.test/api/releases/files/releases/ULTRON.apk',
      },
      {'url': 'http://api.example.test/api/releases/files/releases/ULTRON.apk'},
      {
        'url': 'https://api.example.test/api/releases/files/releases/ULTRON.apk?token=unsafe',
      },
      {'sha256': 'invalid'},
      {'size': 0},
      {'build': -1},
    ]) {
      expect(
        () => AppRelease.parse({...data, ...change}, origin),
        throwsFormatException,
      );
    }
  });
}
