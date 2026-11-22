import 'dart:convert';
import 'package:http/http.dart' as http;
import '../domain/access.dart';
import '../domain/models.dart';
import 'repository.dart';

/// Tokens live only in memory. Relaunching the app requires sign-in.
class CloudflareRepository extends UnconfiguredRepository {
  CloudflareRepository({required Uri baseUrl, http.Client? client, this.onUnauthorized})
    : _base = baseUrl, _client = client ?? http.Client() {
    if ((baseUrl.scheme != 'https' && !(baseUrl.scheme == 'http' && ['127.0.0.1','localhost'].contains(baseUrl.host))) ||
        baseUrl.userInfo.isNotEmpty || baseUrl.hasQuery || baseUrl.hasFragment || !['','/'].contains(baseUrl.path)) {
      throw ArgumentError('Use an HTTPS API origin, or loopback HTTP for local development.');
    }
  }
  final Uri _base;
  final http.Client _client;
  final void Function()? onUnauthorized;
  String? _token;
  AppUser? _user;
  int _epoch = 0;
  @override
  AppUser? get currentUser => _user;
  void close() => _client.close();

  Future<({Map<String,dynamic> data, Map<String,String> headers})> _request(String method, String path,
      {Map<String,Object?>? body, bool authenticated = true}) async {
    final epoch = _epoch;
    if (authenticated && _token == null) throw const FrontendException('Sign in to continue.');
    final request = http.Request(method, _base.resolve(path))..followRedirects = false;
    request.headers['Accept'] = 'application/json';
    if (authenticated) request.headers['Authorization'] = 'Bearer $_token';
    if (body != null) { request.headers['Content-Type'] = 'application/json'; request.body = jsonEncode(body); }
    try {
      final response = await http.Response.fromStream(await _client.send(request).timeout(const Duration(seconds: 25)))
        .timeout(const Duration(seconds: 25));
      if (epoch != _epoch) throw const FrontendException('The session changed. Sign in again.');
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String,dynamic>) throw const FormatException();
      if (response.statusCode < 200 || response.statusCode >= 300) {
        if (response.statusCode == 401 && authenticated) { _token = null; _user = null; onUnauthorized?.call(); }
        final message = decoded['error'] ?? decoded['message'];
        throw FrontendException(message is String ? message : 'The request was refused. Refresh and try again.');
      }
      return (data: decoded, headers: response.headers);
    } on FrontendException { rethrow; }
    catch (_) { throw const FrontendException('The service could not be reached. Check your connection and try again.'); }
  }

  @override
  Future<String> signIn(String email, String password) async {
    final epoch = _epoch;
    final response = await _request('POST','/api/auth/sign-in/email',
      body: {'email': email.trim(), 'password': password, 'rememberMe': false}, authenticated: false);
    final token = response.headers['set-auth-token'] ?? response.data['token'];
    if (epoch != _epoch || token is! String || token.isEmpty) throw const FrontendException('Sign-in could not finish.');
    _token = token;
    try { await refreshUser(); } catch (_) { _token = null; _user = null; rethrow; }
    return '';
  }
  @override
  Future<void> verify(String challenge, String code) async => throw const FrontendException('Sign in with your registered account.');
  @override
  Future<void> register(String name, String email, String password) async {
    await _request('POST','/api/auth/sign-up/email',body: {'name':name.trim(),'email':email.trim(),'password':password},authenticated:false);
  }
  @override
  Future<void> resetPassword(String email) async => throw const FrontendException('Contact your administrator. Email recovery is not configured yet.');
  @override
  Future<void> signOut() async {
    final token = _token;
    ++_epoch; _token = null; _user = null;
    if (token != null) {
      try {
        final request = http.Request('POST',_base.resolve('/api/auth/sign-out'))..followRedirects=false;
        request.headers.addAll({'Authorization':'Bearer $token','Content-Type':'application/json'});
        request.body='{}';
        await (await _client.send(request).timeout(const Duration(seconds:10))).stream.drain<void>().timeout(const Duration(seconds:10));
      } catch (_) { /* Local sign-out still completes when the service is offline. */ }
    }
  }
  @override
  Future<AppUser> refreshUser() async {
    final response=await _request('GET','/api/me');
    return _user=AppUser.fromJson(response.data['user'] as Map<String,dynamic>);
  }
  @override
  Future<UserPage> listUsers({String search='',int page=0}) async {
    final query=Uri(queryParameters:{'search':search,'page':'$page'}).query;
    final response=await _request('GET','/api/admin/users?$query');
    return UserPage((response.data['users'] as List).map((u)=>AppUser.fromJson(Map<String,dynamic>.from(u as Map))).toList(),hasMore:response.data['hasMore']==true);
  }
  @override
  Future<List<AccessRole>> listRoles() async {
    final response=await _request('GET','/api/admin/roles');
    return (response.data['roles'] as List).map((r)=>AccessRole.fromJson(Map<String,dynamic>.from(r as Map))).toList();
  }
  @override
  Future<void> updateUser(AppUser user,{required String status,required String roleId}) async {
    await _request('PATCH','/api/admin/users/${Uri.encodeComponent(user.id)}',body:{'status':status,'roleId':roleId,'revision':user.revision});
  }
  @override
  Future<void> saveRole({required String id,required String name,required List<String> permissions,int? revision}) async {
    await _request('PUT','/api/admin/roles/${Uri.encodeComponent(id)}',body:{'name':name,'permissions':permissions,'revision':revision});
  }
}
