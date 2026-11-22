import '../domain/models.dart';
import '../domain/access.dart';
import 'repository.dart';

class DemoRepository extends UltronRepository {
  DemoRepository({
    DateTime Function()? clock,
    this.delay = const Duration(milliseconds: 350),
  }) : _clock = clock ?? DateTime.now;

  static const demoEmail = 'owner@example.com';
  static const demoPassword = 'ultron-demo';
  static const demoCode = '123456';
  final DateTime Function() _clock;
  final Duration delay;
  bool _signedIn = false;
  bool _challengeIssued = false;
  int _epoch = 0;
  int _runNumber = 0;
  WorkspaceData? _data;

  @override
  bool get isDemo => true;

  @override
  AppUser? get currentUser => _signedIn ? demoAdmin : null;

  @override
  Future<AppUser> refreshUser() async { _requireSession(); return demoAdmin; }

  @override
  Future<void> register(String name, String email, String password) async {
    throw const FrontendException('Registration needs the connected Cloudflare service. No account was created in this demo.');
  }

  @override
  Future<String> signIn(String email, String password) async {
    final epoch = _epoch;
    await Future<void>.delayed(delay);
    if (epoch != _epoch) {
      throw const FrontendException('Sign-in was cancelled.');
    }
    if (email.trim().toLowerCase() != demoEmail || password != demoPassword) {
      throw const FrontendException(
        'Use the displayed demo account to preview this frontend.',
      );
    }
    _challengeIssued = true;
    return 'frontend-demo-challenge';
  }

  @override
  Future<void> verify(String challenge, String code) async {
    final epoch = _epoch;
    await Future<void>.delayed(delay);
    if (epoch != _epoch ||
        !_challengeIssued ||
        challenge != 'frontend-demo-challenge') {
      throw const FrontendException(
        'Sign in again to request a fresh verification.',
      );
    }
    if (code != demoCode) {
      throw const FrontendException('Incorrect code. The demo code is 123456.');
    }
    _challengeIssued = false;
    _signedIn = true;
  }

  @override
  Future<void> resetPassword(String email) async {
    await Future<void>.delayed(delay);
  }

  @override
  Future<void> signOut() async {
    _epoch++;
    _signedIn = false;
    _challengeIssued = false;
    _data = null;
  }

  void _requireSession() {
    if (!_signedIn) {
      throw const FrontendException('Sign in to access this workspace.');
    }
  }

  @override
  Future<WorkspaceData> loadWorkspace() async {
    await Future<void>.delayed(delay);
    _requireSession();
    return _data ??= _seed();
  }

  @override
  Future<WorkspaceData> requestRun(
    String workflowId, {
    required bool preview,
  }) async {
    await Future<void>.delayed(delay);
    _requireSession();
    final data = _data ??= _seed();
    final matches = data.workflows.where((item) => item.id == workflowId);
    if (matches.isEmpty) {
      throw const FrontendException('This workflow is unavailable.');
    }
    final workflow = matches.first;
    _data = data.copyWith(
      runs: List.unmodifiable([
        WorkflowRun(
          id: 'demo-request-${++_runNumber}',
          workflow: '${workflow.name}${preview ? ' · Preview' : ''}',
          marketplace: workflow.marketplace,
          status: RunStatus.completed,
          started: 'Demo request',
          duration: 'Simulated',
          note: 'Request simulated. No portal, inventory, workbook or live workflow was changed.',
        ),
        ...data.runs,
      ]),
    );
    return _data!;
  }

  @override
  Future<WorkspaceData> decide(String id, ApprovalStatus decision) async {
    await Future<void>.delayed(delay);
    _requireSession();
    final data = _data ??= _seed();
    final matches = data.approvals.where((item) => item.id == id);
    if (matches.isEmpty || decision == ApprovalStatus.pending) {
      throw const FrontendException('This decision is unavailable.');
    }
    final request = matches.first;
    if (request.status != ApprovalStatus.pending) {
      throw const FrontendException('This request already has a decision.');
    }
    if (!_clock().isBefore(request.expiresAt)) {
      throw const FrontendException(
        'This request has expired. Ask for a fresh proposal.',
      );
    }
    _data = data.copyWith(
      approvals: List.unmodifiable(
        data.approvals.map(
          (item) => item.id == id ? item.decided(decision) : item,
        ),
      ),
    );
    return _data!;
  }

  @override
  Future<WorkspaceData> sendMessage(String text) async {
    await Future<void>.delayed(delay);
    _requireSession();
    if (text.trim().isEmpty || text.length > 2000) {
      throw const FrontendException(
        'Enter a message of up to 2,000 characters.',
      );
    }
    final data = _data ??= _seed();
    final known = RegExp(
      'myntra|blocked|login|report|attention',
      caseSensitive: false,
    ).hasMatch(text);
    _data = data.copyWith(
      messages: List.unmodifiable([
        ...data.messages,
        AgentMessage(text: text.trim(), fromOwner: true),
        AgentMessage(
          text: known
              ? 'In this demo, Myntra MAIN needs a fresh sign-in. Its figures are excluded from the morning report. Review the connection before requesting a rerun.'
              : 'This is a demo conversation. A connected agent would investigate your request using authorised tools and attach source evidence. Protected changes require a separate approval.',
          fromOwner: false,
          sources: known
              ? const ['Demo run history', 'Demo account health']
              : const [],
        ),
      ]),
    );
    return _data!;
  }

  WorkspaceData _seed() => WorkspaceData(
    workflows: const [
      Workflow(
        id: 'zero-td',
        name: 'Myntra zero TD',
        marketplace: 'Myntra',
        schedule: 'Every 2 hours, Mon–Sat + 10:00 daily',
        description: 'Find live styles selling at MRP.',
        status: RunStatus.running,
        updated: '09:38 IST',
      ),
      Workflow(
        id: 'morning',
        name: 'Morning sale report',
        marketplace: 'All',
        schedule: 'Daily · 09:30 IST',
        description: 'Channel-wise sales with source coverage.',
        status: RunStatus.partial,
        updated: '09:34 IST',
      ),
      Workflow(
        id: 'ajio-spf',
        name: 'AJIO SPF master',
        marketplace: 'AJIO',
        schedule: 'Daily · 09:00 IST',
        description:
            'Claims and return receipts. Tickets and replies only Wed + Sat.',
        status: RunStatus.completed,
        updated: '09:12 IST',
      ),
      Workflow(
        id: 'myntra-reports',
        name: 'Myntra daily reports',
        marketplace: 'Myntra',
        schedule: 'Daily · 09:30 IST',
        description: 'Portal reports and return delivery workbook.',
        status: RunStatus.blocked,
        updated: '09:32 IST',
      ),
      Workflow(
        id: 'inventory',
        name: 'Inventory push',
        marketplace: 'All',
        schedule: 'Every 3 hours',
        description: 'Run the existing inventory working within its rules.',
        status: RunStatus.running,
        updated: '09:00 IST',
      ),
      Workflow(
        id: 'flipkart-price',
        name: 'Flipkart pricing',
        marketplace: 'Flipkart',
        schedule: 'Daily · 08:00 IST',
        description: 'Apply the owner-defined Final TP within portal limits.',
        status: RunStatus.completed,
        updated: '08:06 IST',
      ),
    ],
    runs: List.unmodifiable([
      const WorkflowRun(
        id: 'morning',
        workflow: 'Morning sale report',
        marketplace: 'All',
        status: RunStatus.partial,
        started: '09:30 IST',
        duration: '4 min',
        note: 'AJIO and Flipkart included. Myntra unavailable and excluded.',
      ),
      const WorkflowRun(
        id: 'ajio-spf',
        workflow: 'AJIO SPF master',
        marketplace: 'AJIO',
        status: RunStatus.completed,
        started: '09:00 IST',
        duration: '12 min',
        note: 'Example report completed. No live records are loaded.',
      ),
      const WorkflowRun(
        id: 'inventory',
        workflow: 'Inventory push',
        marketplace: 'All',
        status: RunStatus.running,
        started: '09:00 IST',
        duration: 'In progress',
        note: 'Example working in progress. No real inventory is being pushed.',
      ),
      const WorkflowRun(
        id: 'myntra-reports',
        workflow: 'Myntra daily reports',
        marketplace: 'Myntra',
        status: RunStatus.blocked,
        started: '09:30 IST',
        duration: '2 min',
        note:
            'MAIN requires a fresh sign-in. Human verification remains manual.',
      ),
      const WorkflowRun(
        id: 'zero-td',
        workflow: 'Myntra zero TD',
        marketplace: 'Myntra',
        status: RunStatus.running,
        started: '09:38 IST',
        duration: 'In progress',
        note:
            'Example style check. No buyer-site requests are made by this app.',
      ),
      const WorkflowRun(
        id: 'flipkart-price',
        workflow: 'Flipkart pricing',
        marketplace: 'Flipkart',
        status: RunStatus.completed,
        started: '08:00 IST',
        duration: '6 min',
        note: 'Example owner-defined Final TP working completed.',
      ),
      ...List.generate(
        21,
        (index) => WorkflowRun(
          id: 'earlier-$index',
          workflow: 'Earlier scheduled report ${index + 1}',
          marketplace: const ['Myntra', 'AJIO', 'Flipkart'][index % 3],
          status: RunStatus.completed,
          started: 'Earlier today',
          duration: 'Completed',
          note: 'Synthetic earlier run for the demo summary.',
        ),
      ),
    ]),
    reports: const [
      ReportFile(
        id: 'morning',
        name: 'Morning sale report',
        period: 'Daily',
        updated: 'Today · 09:34 IST',
        sources: [
          SourceCoverage('AJIO', available: true),
          SourceCoverage('Flipkart', available: true),
          SourceCoverage(
            'Myntra',
            available: false,
            note: 'MAIN requires sign-in; figures excluded.',
          ),
        ],
      ),
      ReportFile(
        id: 'ajio',
        name: 'AJIO SPF master',
        period: 'Daily',
        updated: 'Today · 09:12 IST',
        sources: [SourceCoverage('AJIO', available: true)],
      ),
      ReportFile(
        id: 'returns',
        name: 'Return analysis',
        period: 'Monthly',
        updated: 'Example monthly snapshot',
        sources: [
          SourceCoverage('Myntra', available: true),
          SourceCoverage('AJIO', available: true),
          SourceCoverage('Flipkart', available: true),
        ],
      ),
      ReportFile(
        id: 'flipkart',
        name: 'Flipkart listing file',
        period: 'Daily',
        updated: 'Example daily snapshot',
        sources: [SourceCoverage('Flipkart', available: true)],
      ),
    ],
    approvals: [
      ApprovalRequest(
        id: 'spf-additions',
        title: 'Myntra SPF master',
        additions: 12,
        destination: 'SPF workbook',
        expiresAt: _clock().add(const Duration(minutes: 30)),
      ),
    ],
    connections: const [
      PortalConnection(
        'Myntra',
        'MAIN needs sign-in · DBCC and FMCC available',
        available: false,
      ),
      PortalConnection('AJIO', 'Portal + SRM'),
      PortalConnection('Flipkart', 'Seller account'),
      PortalConnection('Google Drive', 'Reports and workbooks'),
      PortalConnection('OMSGuru', 'Orders and returns'),
      PortalConnection('ERP', 'Return receipts'),
    ],
    messages: const [
      AgentMessage(text: 'Why is the Myntra report blocked?', fromOwner: true),
      AgentMessage(
        text: 'In this demo, MAIN needs a fresh sign-in. Myntra is excluded from the morning report.',
        fromOwner: false,
        sources: ['Demo run history', 'Demo account health'],
      ),
    ],
  );
}
