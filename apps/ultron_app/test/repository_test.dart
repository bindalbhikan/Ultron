import 'package:flutter_test/flutter_test.dart';
import 'package:ultron_app/src/data/demo_repository.dart';
import 'package:ultron_app/src/data/repository.dart';
import 'package:ultron_app/src/domain/models.dart';

Future<void> authenticate(DemoRepository repository) async {
  final challenge = await repository.signIn(
    DemoRepository.demoEmail,
    DemoRepository.demoPassword,
  );
  await repository.verify(challenge, DemoRepository.demoCode);
}

void main() {
  test('protected data requires sign-in and successful verification', () async {
    final repository = DemoRepository(delay: Duration.zero);
    await expectLater(
      repository.loadWorkspace(),
      throwsA(isA<FrontendException>()),
    );
    final challenge = await repository.signIn(
      DemoRepository.demoEmail,
      DemoRepository.demoPassword,
    );
    await expectLater(
      repository.loadWorkspace(),
      throwsA(isA<FrontendException>()),
    );
    await expectLater(
      repository.verify(challenge, '000000'),
      throwsA(isA<FrontendException>()),
    );
    await repository.verify(challenge, DemoRepository.demoCode);
    final data = await repository.loadWorkspace();
    expect(data.runs.length, 27);
    expect(
      data.completedRuns + data.activeRuns + data.blockedRuns,
      data.runs.length,
    );
    expect(data.completedRuns, 24);
    await repository.signOut();
    await expectLater(
      repository.loadWorkspace(),
      throwsA(isA<FrontendException>()),
    );
  });

  test('missing report source remains excluded with its reason', () async {
    final repository = DemoRepository(delay: Duration.zero);
    await authenticate(repository);
    final report = (await repository.loadWorkspace()).reports.first;
    expect(report.isPartial, isTrue);
    final myntra = report.sources.singleWhere(
      (source) => source.name == 'Myntra',
    );
    expect(myntra.available, isFalse);
    expect(myntra.note, contains('excluded'));
  });

  test('approval scope cannot be decided twice or after expiry', () async {
    var now = DateTime.utc(2026, 11, 16, 4);
    final repository = DemoRepository(delay: Duration.zero, clock: () => now);
    await authenticate(repository);
    final request = (await repository.loadWorkspace()).approvals.single;
    await repository.decide(request.id, ApprovalStatus.approved);
    await expectLater(
      repository.decide(request.id, ApprovalStatus.declined),
      throwsA(isA<FrontendException>()),
    );
    await repository.signOut();
    await authenticate(repository);
    final fresh = (await repository.loadWorkspace()).approvals.single;
    now = fresh.expiresAt;
    await expectLater(
      repository.decide(fresh.id, ApprovalStatus.approved),
      throwsA(isA<FrontendException>()),
    );
  });

  test(
    'demo requests stay explicit and unknown workflows are rejected',
    () async {
      final repository = DemoRepository(delay: Duration.zero);
      await authenticate(repository);
      await repository.loadWorkspace();
      final data = await repository.requestRun('inventory', preview: false);
      expect(data.runs.first.note, contains('simulated'));
      expect(data.runs.first.duration, 'Simulated');
      await expectLater(
        repository.requestRun('unknown', preview: true),
        throwsA(isA<FrontendException>()),
      );
    },
  );

  test('sign-out invalidates an in-flight challenge', () async {
    final repository = DemoRepository(delay: const Duration(milliseconds: 5));
    final pending = repository.signIn(
      DemoRepository.demoEmail,
      DemoRepository.demoPassword,
    );
    final expectation = expectLater(pending, throwsA(isA<FrontendException>()));
    await repository.signOut();
    await expectation;
  });

  test(
    'unconfigured live mode never falls back to demo authentication or data',
    () async {
      final repository = UnconfiguredRepository();
      expect(repository.isDemo, isFalse);
      await expectLater(
        repository.signIn(
          DemoRepository.demoEmail,
          DemoRepository.demoPassword,
        ),
        throwsA(isA<FrontendException>()),
      );
      await expectLater(
        repository.loadWorkspace(),
        throwsA(isA<FrontendException>()),
      );
      await expectLater(
        repository.requestRun('inventory', preview: false),
        throwsA(isA<FrontendException>()),
      );
    },
  );
}
