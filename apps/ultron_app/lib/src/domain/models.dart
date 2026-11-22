import 'package:flutter/foundation.dart';
import 'access.dart';

enum SessionPhase { signedOut, verification, signedIn }

enum RunStatus {
  completed('Completed'),
  running('Running'),
  partial('Partial'),
  blocked('Needs login');

  const RunStatus(this.label);
  final String label;
}

enum ApprovalStatus { pending, approved, declined }

@immutable
class SessionState {
  const SessionState({
    this.phase = SessionPhase.signedOut,
    this.busy = false,
    this.error,
    this.challenge,
    this.user,
  });

  final SessionPhase phase;
  final bool busy;
  final String? error;
  final String? challenge;
  final AppUser? user;
}

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
  });

  final String id;
  final String name;
  final String marketplace;
  final String schedule;
  final String description;
  final RunStatus status;
  final String updated;
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
  });

  final String id;
  final String workflow;
  final String marketplace;
  final RunStatus status;
  final String started;
  final String duration;
  final String note;
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
  });
  final String text;
  final bool fromOwner;
  final List<String> sources;
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
  });

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
  int get blockedRuns =>
      runs.where((run) => run.status == RunStatus.blocked).length;
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
  );
}

class FrontendException implements Exception {
  const FrontendException(this.message);
  final String message;
  @override
  String toString() => message;
}
