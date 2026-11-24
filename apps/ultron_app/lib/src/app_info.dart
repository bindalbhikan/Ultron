abstract final class AppInfo {
  static const name = 'ULTRON';
  static const version = String.fromEnvironment(
    'APP_VERSION',
    defaultValue: '0.1.0',
  );
  static const build = int.fromEnvironment('BUILD_NUMBER', defaultValue: 1);
  static const developer = 'Bhikan Deshmukh';
  static const flutterVersion = '3.50.0';
  static const dartVersion = '3.14.0';
}
