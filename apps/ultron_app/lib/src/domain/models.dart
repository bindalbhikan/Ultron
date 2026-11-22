import 'package:flutter/foundation.dart';

import 'access.dart';

enum SessionPhase { signedOut, signedIn }

@immutable
class SessionState {
  const SessionState({
    this.phase = SessionPhase.signedOut,
    this.busy = false,
    this.error,
    this.user,
  });

  final SessionPhase phase;
  final bool busy;
  final String? error;
  final AppUser? user;
}

class FrontendException implements Exception {
  const FrontendException(this.message);
  final String message;
  @override
  String toString() => message;
}
