from __future__ import annotations

import multiprocessing
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from anc_canonical import canonical_digest
from ordivon_host import HostExtensionPort, HostStorage
from ordivon_host.journal import JournalCorruption
from test_ordivon_harness_oh5 import (
    TASK_ID,
    _RecoveryRuntime,
    _assign,
    _create_task,
)
from test_provider_call_durability import _MutableClock, _RaceAdapter, _needs_input
from test_provider_call_recovery import (
    _provider_failure,
    _provider_result,
    _provider_state,
)
from test_runner_r0_r1 import _plan

from ordivon_harness import (
    HarnessHost,
    HarnessLifecycleError,
    HarnessProviderCallRecoveryRequired,
    HarnessRunner,
    HarnessSuperseded,
)
from ordivon_harness.event_kinds import HARNESS_RUN_RECOVERY_RECORDED
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import (
    AgentTurnRequest,
    AgentTurnResult,
    HostHarnessRunStore,
    RunStopCode,
    ScriptedTurnAdapter,
    static_provider_request_digest,
)
from ordivon_harness.recovery_controller import NativeRunRecoveryController


class _ReplayOnlyRaceAdapter:
    adapter_id = _RaceAdapter.adapter_id
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        del request
        self.calls += 1
        raise AssertionError("late durable Provider result was not replayed")


def _complete_provider_process(
    directory: str,
    ready,
    release,
    result_queue,
) -> None:
    clock = _MutableClock()
    try:
        with HostStorage(directory) as storage:
            host = HarnessHost(storage, clock_ms=clock)
            store = HostHarnessRunStore(
                host, host.load_current_assignment(TASK_ID)
            )
            dispatching = store.load_current_provider_call()
            store.bind_state(dispatching.state)
            ready.set()
            if not release.wait(10):
                raise TimeoutError("completion release was not signalled")
            completed = store.complete_provider_call(
                dispatching, _provider_result()
            )
            result_queue.put(
                (
                    "completed",
                    completed.record.status.value,
                    store.provider_outcome_requires_resume,
                )
            )
    except Exception as error:  # noqa: BLE001 - child result is asserted by parent.
        result_queue.put(("error", type(error).__name__, str(error)))


def _recover_provider_process(
    directory: str,
    ready,
    release,
    result_queue,
) -> None:
    clock = _MutableClock()
    try:
        with HostStorage(directory) as storage:
            host = HarnessHost(storage, clock_ms=clock)
            workspace_id = host.load_current_assignment(
                TASK_ID
            ).assignment.workspace_ref
            runtime = _RecoveryRuntime()
            if workspace_id is not None:
                runtime.workspaces.add(workspace_id)
            ready.set()
            if not release.wait(10):
                raise TimeoutError("recovery release was not signalled")
            recovery = NativeRunRecoveryController(host, runtime).recover(TASK_ID)
            result_queue.put(
                (
                    "recovered",
                    recovery.recovery.assessment.workspace_status,
                    recovery.abandonment is None,
                )
            )
    except Exception as error:  # noqa: BLE001 - child result is asserted by parent.
        result_queue.put(("error", type(error).__name__, str(error)))


class ProviderRecoveryRaceTests(unittest.TestCase):
    def _prepare_dispatching(
        self, directory: str, clock: _MutableClock, runtime: _RecoveryRuntime
    ):
        with HostStorage(directory) as storage:
            _create_task(storage, clock)
            host, committed, _, _ = _assign(storage, clock, runtime)
            store = HostHarnessRunStore(host, committed)
            store.bind_state(_provider_state())
            source = store.assignment_provider_source()
            request_digest = canonical_digest(
                {"request": "provider-recovery-race-process"}
            )
            provider_request_digest = canonical_digest(
                {"providerRequest": "provider-recovery-race-process"}
            )
            claimed = store.claim_provider_call(
                source=source,
                turn_id="turn:provider-recovery-race:process",
                turn_sequence=1,
                request_digest=request_digest,
                provider_request_digest=provider_request_digest,
                adapter_id=_RaceAdapter.adapter_id,
                requested_model_id=ScriptedTurnAdapter.model_id,
                holder_id="holder:provider-recovery-race:process",
                ttl_ms=10_000,
            )
            dispatching = store.mark_provider_call_dispatching(claimed)
            workspace_id = committed.assignment.workspace_ref
            if workspace_id is not None:
                runtime.workspaces.add(workspace_id)
            return dispatching, workspace_id

    def test_late_provider_completion_survives_recovery_and_requires_resume(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                paused = HarnessRunner(
                    HarnessHost(storage, clock_ms=clock),
                    runtime=runtime,
                    adapter=ScriptedTurnAdapter((_needs_input(),)),
                ).run(_plan())
                self.assertTrue(paused.paused)
                workspace_id = HarnessHost(
                    storage, clock_ms=clock
                ).load_current_assignment(TASK_ID).assignment.workspace_ref
                assert workspace_id is not None
                runtime.workspaces.add(workspace_id)

            invoked = threading.Event()
            release = threading.Event()
            physical_calls = [0]
            calls_lock = threading.Lock()
            worker_outcome: list[object] = []

            def worker() -> None:
                try:
                    with HostStorage(directory) as storage:
                        result = HarnessRunner(
                            HarnessHost(storage, clock_ms=clock),
                            runtime=runtime,
                            adapter=_RaceAdapter(
                                invoked,
                                release,
                                physical_calls,
                                calls_lock,
                            ),
                        ).resume(
                            TASK_ID,
                            additional_messages=(
                                {
                                    "role": "user",
                                    "content": "Resume across the Recovery race.",
                                },
                            ),
                        )
                    worker_outcome.append(result)
                except Exception as error:  # noqa: BLE001 - assert the exact fence.
                    worker_outcome.append(error)

            thread = threading.Thread(target=worker, name="provider-recovery-race")
            thread.start()
            self.assertTrue(invoked.wait(5), "Provider invocation did not start")

            with HostStorage(directory) as storage:
                recovery = NativeRunRecoveryController(
                    HarnessHost(storage, clock_ms=clock), runtime
                ).recover(TASK_ID)
                self.assertIsNone(recovery.abandonment)
                self.assertFalse(recovery.recovery.assessment.safe_to_abandon)
                self.assertEqual(
                    recovery.recovery.assessment.workspace_status,
                    "retained",
                )

            release.set()
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(physical_calls, [1])
            self.assertEqual(len(worker_outcome), 1)
            self.assertIsInstance(
                worker_outcome[0], HarnessProviderCallRecoveryRequired
            )
            self.assertIn(workspace_id, runtime.workspaces)
            self.assertFalse(
                any(name == "workspace.close" for name, _ in runtime.calls)
            )

            with HostStorage(directory) as storage:
                host = HarnessHost(storage, clock_ms=clock)
                current = host.load_current_assignment(TASK_ID)
                provider = HostHarnessRunStore(
                    host, current
                ).load_current_provider_call()
                self.assertEqual(provider.record.status.value, "completed")
                self.assertIsNotNone(host.load_current_native_run_recovery(TASK_ID))
                kinds = [
                    str(row["event_kind"])
                    for row in storage.journal.connection.execute(
                        "SELECT event_kind FROM events WHERE stream_id = ? "
                        "ORDER BY stream_revision",
                        (TASK_ID,),
                    ).fetchall()
                ]
                self.assertEqual(kinds.count("harness.run-recovery-recorded"), 1)
                self.assertEqual(kinds.count("harness.provider-call-completed"), 2)
                validate_history(storage)

            replay = _ReplayOnlyRaceAdapter()
            with HostStorage(directory) as storage:
                host = HarnessHost(storage, clock_ms=clock)
                resumed = HarnessRunner(
                    host,
                    runtime=runtime,
                    adapter=replay,
                ).resume(TASK_ID)
                self.assertEqual(
                    resumed.loop_result.stop_code,
                    RunStopCode.CANDIDATE_COMPLETED,
                )
                self.assertIsNotNone(resumed.recorded)
                self.assertEqual(replay.calls, 0)
                self.assertIsNotNone(host.load_current_run(TASK_ID))
                with self.assertRaises(HarnessLifecycleError):
                    host.load_current_native_run_recovery(TASK_ID)
                validate_history(storage)

    def test_repeated_late_completion_is_idempotent_but_still_fenced(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(storage, clock, runtime)
                store = HostHarnessRunStore(host, committed)
                state = _provider_state()
                store.bind_state(state)
                source = store.assignment_provider_source()
                request_digest = canonical_digest(
                    {"request": "provider-recovery-race-idempotent"}
                )
                provider_request_digest = canonical_digest(
                    {"providerRequest": "provider-recovery-race-idempotent"}
                )
                claimed = store.claim_provider_call(
                    source=source,
                    turn_id="turn:provider-recovery-race:idempotent",
                    turn_sequence=1,
                    request_digest=request_digest,
                    provider_request_digest=provider_request_digest,
                    adapter_id=_RaceAdapter.adapter_id,
                    requested_model_id=ScriptedTurnAdapter.model_id,
                    holder_id="holder:provider-recovery-race:idempotent",
                    ttl_ms=10_000,
                )
                dispatching = store.mark_provider_call_dispatching(claimed)
                runtime.workspaces.add(committed.assignment.workspace_ref)
                recovery = NativeRunRecoveryController(host, runtime).recover(TASK_ID)
                result = _provider_result()
                first = store.complete_provider_call(dispatching, result)
                self.assertTrue(store.provider_outcome_requires_resume)
                events_before = storage.journal.event_count(TASK_ID)
                second = store.complete_provider_call(dispatching, result)
                self.assertEqual(first.record, second.record)
                self.assertTrue(store.provider_outcome_requires_resume)
                self.assertEqual(storage.journal.event_count(TASK_ID), events_before)

                drifted = replace(
                    result,
                    model_call_id="model-call:provider-recovery:drifted",
                    raw_response_digest=canonical_digest(
                        {"providerRecovery": "drifted"}
                    ),
                )
                with self.assertRaises(HarnessProviderCallRecoveryRequired):
                    store.complete_provider_call(dispatching, drifted)
                self.assertEqual(storage.journal.event_count(TASK_ID), events_before)
                self.assertEqual(
                    recovery.recovery.assessment.workspace_status, "retained"
                )
                validate_history(storage)

    def test_recovery_evidence_drift_rejects_late_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(storage, clock, runtime)
                store = HostHarnessRunStore(host, committed)
                store.bind_state(_provider_state())
                source = store.assignment_provider_source()
                request_digest = canonical_digest(
                    {"request": "provider-recovery-race-evidence-drift"}
                )
                provider_request_digest = canonical_digest(
                    {"providerRequest": "provider-recovery-race-evidence-drift"}
                )
                claimed = store.claim_provider_call(
                    source=source,
                    turn_id="turn:provider-recovery-race:evidence-drift",
                    turn_sequence=1,
                    request_digest=request_digest,
                    provider_request_digest=provider_request_digest,
                    adapter_id=_RaceAdapter.adapter_id,
                    requested_model_id=ScriptedTurnAdapter.model_id,
                    holder_id="holder:provider-recovery-race:evidence-drift",
                    ttl_ms=10_000,
                )
                dispatching = store.mark_provider_call_dispatching(claimed)
                runtime.workspaces.add(committed.assignment.workspace_ref)
                recovery = NativeRunRecoveryController(host, runtime).recover(TASK_ID)
                evidence = dict(recovery.recovery.assessment.workspace_evidence)
                provider = dict(evidence["providerCallReconciliation"])
                provider["recordDigest"] = canonical_digest(
                    {"drifted": "recovery-evidence"}
                )
                evidence["providerCallReconciliation"] = provider
                drifted_assessment = replace(
                    recovery.recovery.assessment,
                    workspace_evidence=evidence,
                )
                drifted_recovery = replace(
                    recovery.recovery,
                    assessment=drifted_assessment,
                )
                object_count = len(
                    tuple((Path(directory) / "objects").glob("*.json"))
                )
                with patch.object(
                    host,
                    "load_current_native_run_recovery",
                    return_value=drifted_recovery,
                ):
                    with self.assertRaises(HarnessSuperseded):
                        store.complete_provider_call(
                            dispatching, _provider_result()
                        )
                self.assertEqual(
                    len(tuple((Path(directory) / "objects").glob("*.json"))),
                    object_count,
                )
                current = HostHarnessRunStore(
                    host, host.load_current_assignment(TASK_ID)
                ).load_current_provider_call()
                self.assertEqual(current.record, dispatching.record)
                validate_history(storage)

    def test_multiprocess_recovery_wins_then_late_completion_commits(
        self,
    ) -> None:
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            dispatching, workspace_id = self._prepare_dispatching(
                directory, clock, runtime
            )
            ready = context.Event()
            release = context.Event()
            queue = context.Queue()
            process = context.Process(
                target=_complete_provider_process,
                args=(directory, ready, release, queue),
            )
            process.start()
            self.assertTrue(ready.wait(5))
            with HostStorage(directory) as storage:
                recovery = NativeRunRecoveryController(
                    HarnessHost(storage, clock_ms=clock), runtime
                ).recover(TASK_ID)
                self.assertEqual(
                    recovery.recovery.assessment.workspace_status, "retained"
                )
            release.set()
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(queue.get(timeout=2), ("completed", "completed", True))
            with HostStorage(directory) as storage:
                host = HarnessHost(storage, clock_ms=clock)
                current = HostHarnessRunStore(
                    host, host.load_current_assignment(TASK_ID)
                ).load_current_provider_call()
                self.assertEqual(
                    current.record.previous_record_digest, dispatching.record.digest
                )
                self.assertEqual(current.record.status.value, "completed")
                self.assertIn(workspace_id, runtime.workspaces)
                validate_history(storage)

    def test_multiprocess_completion_wins_and_recovery_requires_resume(
        self,
    ) -> None:
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            _, _ = self._prepare_dispatching(directory, clock, runtime)
            ready = context.Event()
            release = context.Event()
            queue = context.Queue()
            process = context.Process(
                target=_recover_provider_process,
                args=(directory, ready, release, queue),
            )
            process.start()
            self.assertTrue(ready.wait(5))
            with HostStorage(directory) as storage:
                host = HarnessHost(storage, clock_ms=clock)
                store = HostHarnessRunStore(
                    host, host.load_current_assignment(TASK_ID)
                )
                dispatching = store.load_current_provider_call()
                store.bind_state(dispatching.state)
                completed = store.complete_provider_call(
                    dispatching, _provider_result()
                )
                self.assertEqual(completed.record.status.value, "completed")
                self.assertFalse(store.provider_outcome_requires_resume)
            release.set()
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            outcome = queue.get(timeout=2)
            self.assertEqual(outcome[0], "error")
            self.assertEqual(outcome[1], "HarnessLifecycleError")
            self.assertIn("requires resume", outcome[2])
            with HostStorage(directory) as storage:
                self.assertEqual(
                    storage.journal.connection.execute(
                        "SELECT COUNT(*) AS count FROM events "
                        "WHERE stream_id = ? AND event_kind = ?",
                        (TASK_ID, "harness.run-recovery-recorded"),
                    ).fetchone()["count"],
                    0,
                )
                validate_history(storage)

    def test_late_failed_and_unknown_outcomes_are_durable_and_fenced(
        self,
    ) -> None:
        for dispatch_safety, expected_status in (
            ("provider_rejected", "failed"),
            ("dispatch_ambiguous", "unknown"),
        ):
            with (
                self.subTest(dispatch_safety=dispatch_safety),
                tempfile.TemporaryDirectory() as directory,
            ):
                clock = _MutableClock()
                runtime = _RecoveryRuntime()
                dispatching, _ = self._prepare_dispatching(
                    directory, clock, runtime
                )
                with HostStorage(directory) as storage:
                    host = HarnessHost(storage, clock_ms=clock)
                    store = HostHarnessRunStore(
                        host, host.load_current_assignment(TASK_ID)
                    )
                    retained = store.load_current_provider_call()
                    store.bind_state(retained.state)
                    recovery = NativeRunRecoveryController(
                        host, runtime
                    ).recover(TASK_ID)
                    failure = _provider_failure(
                        dispatching, dispatch_safety=dispatch_safety
                    )
                    terminal = store.fail_provider_call(
                        dispatching, failure=failure
                    )
                    self.assertEqual(terminal.record.status.value, expected_status)
                    self.assertTrue(store.provider_outcome_requires_resume)
                    events_before = storage.journal.event_count(TASK_ID)
                    repeated = store.fail_provider_call(
                        dispatching, failure=failure
                    )
                    self.assertEqual(repeated.record, terminal.record)
                    self.assertTrue(store.provider_outcome_requires_resume)
                    self.assertEqual(
                        storage.journal.event_count(TASK_ID), events_before
                    )
                    self.assertEqual(
                        recovery.recovery.assessment.workspace_status, "retained"
                    )
                    validate_history(storage)

    def test_history_rejects_forged_recovery_resolution_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            dispatching, _ = self._prepare_dispatching(
                directory, clock, runtime
            )
            with HostStorage(directory) as storage:
                host = HarnessHost(storage, clock_ms=clock)
                NativeRunRecoveryController(host, runtime).recover(TASK_ID)
                extension = HostExtensionPort(storage, host.kernel)
                current = extension.load(TASK_ID)
                extension.append_preserving(
                    task_id=TASK_ID,
                    expected_revision=current.projection.revision,
                    event_id="event:provider-recovery-race:forged-resolution",
                    kind=HARNESS_RUN_RECOVERY_RECORDED,
                    updates={
                        "harnessRunRecoveryResolvedProviderCallDigest": (
                            dispatching.record.digest
                        ),
                        "harnessRunRecoveryResolvedProviderCallObjectDigest": (
                            dispatching.record_object.digest
                        ),
                        "harnessRunRecoveryResolvedPreviousProviderCallDigest": (
                            dispatching.record.previous_record_digest
                            or dispatching.record.digest
                        ),
                    },
                    referenced_objects=(dispatching.record_object,),
                    label="Forged Recovery Provider resolution fixture",
                )
                with self.assertRaisesRegex(
                    JournalCorruption, "Recovery Provider resolution"
                ):
                    validate_history(storage)


if __name__ == "__main__":
    unittest.main()
