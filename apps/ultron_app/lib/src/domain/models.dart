import 'package:flutter/foundation.dart';

import 'access.dart';

enum SessionPhase { signedOut, signedIn }

enum RunStatus {
  completed('Completed'),
  running('Running'),
  partial('Partial'),
  blocked('Needs login'),
  failed('Failed'),
  never('Not run yet');

  const RunStatus(this.label);
  final String label;
}

enum ApprovalStatus { pending, approved, declined }

@immutable
class Workflow {
  const Workflow({
    required this.id,
    required this.name,
    required this.marketplace,
    required this.schedule,
    required this.description,
    required this.status,
    required this.updated,
    this.action,
    this.auto = false,
    this.fields = const {},
  });
  final String id;
  final String name;
  final String marketplace;
  final String schedule;
  final String description;
  final RunStatus status;
  final String updated;

  /// The working's name in the worker's AGENT_ACTIONS when it can be started from here; null otherwise.
  final String? action;

  /// Only makes a report (the agent may run it at once).
  final bool auto;
  final Map<String, dynamic> fields;
}

@immutable
class WorkflowRun {
  const WorkflowRun({
    required this.id,
    required this.workflow,
    required this.marketplace,
    required this.status,
    required this.started,
    required this.duration,
    required this.note,
    this.controllable = false,
  });

  final String id;
  final String workflow;
  final String marketplace;
  final RunStatus status;
  final String started;
  final String duration;
  final String note;
  final bool controllable;
}

@immutable
class SourceCoverage {
  const SourceCoverage(this.name, {required this.available, this.note});
  final String name;
  final bool available;
  final String? note;
}

@immutable
class ReportFile {
  const ReportFile({
    required this.id,
    required this.name,
    required this.period,
    required this.updated,
    required this.sources,
  });

  final String id;
  final String name;
  final String period;
  final String updated;
  final List<SourceCoverage> sources;
  bool get isPartial => sources.any((source) => !source.available);
}

@immutable
class ApprovalRequest {
  const ApprovalRequest({
    required this.id,
    required this.title,
    required this.additions,
    required this.destination,
    required this.expiresAt,
    this.status = ApprovalStatus.pending,
  });

  final String id;
  final String title;
  final int additions;
  final String destination;
  final DateTime expiresAt;
  final ApprovalStatus status;

  ApprovalRequest decided(ApprovalStatus decision) => ApprovalRequest(
    id: id,
    title: title,
    additions: additions,
    destination: destination,
    expiresAt: expiresAt,
    status: decision,
  );
}

@immutable
class PortalConnection {
  const PortalConnection(this.name, this.detail, {this.available = true});
  final String name;
  final String detail;
  final bool available;
}

@immutable
class AgentMessage {
  const AgentMessage({
    required this.text,
    required this.fromOwner,
    this.sources = const [],
    this.files = const [],
    this.pending = false,
  });
  final String text;
  final bool fromOwner;
  final List<String> sources;

  /// Files the agent attached to its answer (a run's picture or sheet, a dynamic working's result).
  final List<AgentFile> files;
  final bool pending;
}

/// One file of an agent answer, kept with the conversation for 30 days.
@immutable
class AgentFile {
  const AgentFile({
    required this.id,
    required this.name,
    required this.mime,
    required this.size,
    this.caption = '',
  });
  final String id;
  final String name;
  final String mime;
  final int size;
  final String caption;
  bool get isImage => mime.startsWith('image/');
}

/// One start time of the worker's cron schedule (worker/src/worker.js SCHEDULE).
@immutable
class ScheduleItem {
  const ScheduleItem({
    required this.time,
    required this.when,
    required this.name,
    required this.portal,
    this.id = '',
    this.cron = '',
    this.revision = 0,
    this.enabled = true,
  });

  /// "7:00 AM"; [when] is the rest ("daily", "on the 10th", "Mon-Sat").
  final String time, when, name, portal;
  final String id, cron;
  final int revision;
  final bool enabled;

  /// Minutes after midnight IST, to sort and to find the next one.
  int get minutes {
    final m = RegExp(r'^(\d{1,2}):(\d{2})\s*(AM|PM)$').firstMatch(time);
    if (m == null) return 0;
    final h = int.parse(m.group(1)!) % 12 + (m.group(3) == 'PM' ? 12 : 0);
    return h * 60 + int.parse(m.group(2)!);
  }

  bool get daily => when.startsWith('daily');
}

@immutable
class WorkspaceData {
  const WorkspaceData({
    required this.workflows,
    required this.runs,
    required this.reports,
    required this.approvals,
    required this.connections,
    required this.messages,
    this.schedule = const [],
  });

  final List<ScheduleItem> schedule;

  final List<Workflow> workflows;
  final List<WorkflowRun> runs;
  final List<ReportFile> reports;
  final List<ApprovalRequest> approvals;
  final List<PortalConnection> connections;
  final List<AgentMessage> messages;

  int get completedRuns => runs
      .where(
        (run) =>
            run.status == RunStatus.completed ||
            run.status == RunStatus.partial,
      )
      .length;
  int get activeRuns =>
      runs.where((run) => run.status == RunStatus.running).length;
  int get blockedRuns => runs
      .where(
        (run) =>
            run.status == RunStatus.blocked || run.status == RunStatus.failed,
      )
      .length;
  int get pendingApprovals =>
      approvals.where((item) => item.status == ApprovalStatus.pending).length;

  WorkspaceData copyWith({
    List<WorkflowRun>? runs,
    List<ApprovalRequest>? approvals,
    List<AgentMessage>? messages,
  }) => WorkspaceData(
    workflows: workflows,
    runs: runs ?? this.runs,
    reports: reports,
    approvals: approvals ?? this.approvals,
    connections: connections,
    messages: messages ?? this.messages,
    schedule: schedule,
  );
}

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
