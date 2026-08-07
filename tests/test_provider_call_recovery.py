from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from anc_canonical import canonical_digest
from ordivon_host import HostStorage, TaskState
from test_ordivon_harness_oh5 import (
    TASK_ID,
    _RecoveryRuntime,
    _assign,
    _create_task,
)

from ordivon_harness import (
    HarnessLifecycleError,
    HarnessProviderCallFailureReceipt,
    HarnessRunner,
)
from ordivon_harness.cli import build_parser
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    AgentTurnResult,
    HarnessRunState,
    HostHarnessRunStore,
    ScriptedTurnAdapter,
)
from ordivon_harness.recovery_controller import NativeRunRecoveryController


class _MutableClock:
    def __init__(self, value: int = 100_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


def _provider_state() -> HarnessRunState:
    return HarnessRunState(
        messages=({"role": "user", "content": "recover provider call"},),
        observations=(),
        remaining_budget={
            "modelCalls": 4,
            "toolCalls": 4,
            "observationBytes": 65_536,
            "wallTimeMs": 30_000,
        },
        requested_model_id=ScriptedTurnAdapter.model_id,
        effective_model_id=None,
    )


def _provider_result() -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id="model-call:provider-recovery:completed",
        model_id=ScriptedTurnAdapter.model_id,
        content=None,
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Durable Provider result awaits replay.",
        ),
        usage={},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"providerRecovery": "completed"}),
    )


def _provider_failure(
    retained,
    *,
    dispatch_safety: str,
) -> HarnessProviderCallFailureReceipt:
    return HarnessProviderCallFailureReceipt(
        provider_call_id=retained.record.provider_call_id,
        request_digest=retained.record.request_digest,
        provider_request_digest=retained.record.provider_request_digest,
        failure_code=(
            "provider_transport_failed"
            if dispatch_safety == "dispatch_ambiguous"
            else "provider_rejected"
        ),
        dispatch_safety=dispatch_safety,
        detail="Provider recovery failure fixture.",
    )


class ProviderCallRecoveryTests(unittest.TestCase):
    def _claim(self, host, committed, *, ttl_ms: int = 1_000):
        store = HostHarnessRunStore(host, committed)
        state = _provider_state()
        store.bind_state(state)
        source = store.assignment_provider_source()
        arguments = {
            "source": source,
            "turn_id": "turn:provider-recovery:1",
            "turn_sequence": 1,
            "request_digest": canonical_digest(
                {"request": "provider-recovery"}
            ),
            "provider_request_digest": canonical_digest(
                {"providerRequest": "provider-recovery"}
            ),
            "adapter_id": "ordivon.provider-recovery-fixture.v1",
            "requested_model_id": ScriptedTurnAdapter.model_id,
            "holder_id": "holder:provider-recovery:first",
            "ttl_ms": ttl_ms,
        }
        return store, state, arguments, store.claim_provider_call(**arguments)

    def test_completed_provider_result_requires_resume_without_recovery_side_effects(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(storage, clock, runtime)
                store, _, _, claimed = self._claim(host, committed)
                dispatching = store.mark_provider_call_dispatching(claimed)
                store.complete_provider_call(dispatching, _provider_result())

                calls_before = tuple(runtime.calls)
                with self.assertRaisesRegex(HarnessLifecycleError, "resume"):
                    NativeRunRecoveryController(host, runtime).recover(TASK_ID)

                self.assertEqual(tuple(runtime.calls), calls_before)
                self.assertIn("workspace:oh5:g1", runtime.workspaces)
                with self.assertRaises(HarnessLifecycleError):
                    host.load_current_native_run_recovery(TASK_ID)
                current = HostHarnessRunStore(
                    host, host.load_current_assignment(TASK_ID)
                ).load_current_provider_call()
                self.assertEqual(current.record.status.value, "completed")

    def test_live_claim_requires_resume_or_wait_without_abandonment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(storage, clock, runtime)
                self._claim(host, committed)

                calls_before = tuple(runtime.calls)
                with self.assertRaisesRegex(HarnessLifecycleError, "resume"):
                    NativeRunRecoveryController(host, runtime).recover(TASK_ID)

                self.assertEqual(tuple(runtime.calls), calls_before)
                self.assertIn("workspace:oh5:g1", runtime.workspaces)
                with self.assertRaises(HarnessLifecycleError):
                    host.load_current_native_run_abandonment(TASK_ID)

    def test_expired_undispatched_claim_remains_reclaimable_by_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(storage, clock, runtime)
                _, state, arguments, claimed = self._claim(
                    host, committed, ttl_ms=10
                )
                clock.value = claimed.record.expires_at_ms + 1

                with self.assertRaisesRegex(HarnessLifecycleError, "resume"):
                    NativeRunRecoveryController(host, runtime).recover(TASK_ID)

                resumed = HostHarnessRunStore(
                    host, host.load_current_assignment(TASK_ID)
                )
                resumed.bind_state(state)
                reclaimed = resumed.claim_provider_call(
                    **{
                        **arguments,
                        "holder_id": "holder:provider-recovery:second",
                    }
                )
                self.assertEqual(reclaimed.record.claim_generation, 2)
                self.assertEqual(reclaimed.record.status.value, "claimed")

    def test_dispatching_provider_call_records_unresolved_recovery_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(storage, clock, runtime)
                store, _, _, claimed = self._claim(host, committed)
                retained = store.mark_provider_call_dispatching(claimed)

                result = NativeRunRecoveryController(host, runtime).recover(
                    TASK_ID
                )

                self.assertIsNone(result.abandonment)
                self.assertFalse(result.recovery.assessment.safe_to_abandon)
                evidence = result.recovery.assessment.workspace_evidence
                provider = evidence["providerCallReconciliation"]
                assert isinstance(provider, dict)
                self.assertEqual(provider["status"], "dispatching")
                self.assertEqual(
                    provider["recordDigest"], retained.record.digest
                )
                self.assertFalse(provider["structuredOutcome"])
                provider_unknowns = evidence[
                    "providerCallUnresolvedUnknowns"
                ]
                assert isinstance(provider_unknowns, list)
                self.assertEqual(len(provider_unknowns), 1)
                self.assertIn("DISPATCHING", provider_unknowns[0])
                self.assertIn(
                    provider_unknowns[0],
                    result.recovery.assessment.unresolved_unknowns,
                )
                data = storage.read_task_event(TASK_ID).data
                assert isinstance(data, dict)
                self.assertEqual(
                    data["activeHarnessProviderCallDigest"],
                    retained.record.digest,
                )
                self.assertEqual(
                    storage.journal.get_task(TASK_ID).state,
                    TaskState.BLOCKED,
                )
                validate_history(storage)

    def test_public_runner_recover_uses_protocol_default_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(storage, clock, runtime)
                store, _, _, claimed = self._claim(host, committed)
                store.mark_provider_call_dispatching(claimed)

                result = HarnessRunner(host, runtime=runtime).recover(TASK_ID)

                self.assertEqual(
                    result.recovery.assessment.trigger,
                    "host_restart",
                )
                self.assertIsNone(result.abandonment)

    def test_structured_unknown_requires_resume_without_recovery_side_effects(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(storage, clock, runtime)
                store, _, _, claimed = self._claim(host, committed)
                dispatching = store.mark_provider_call_dispatching(claimed)
                unknown = store.fail_provider_call(
                    dispatching,
                    failure=_provider_failure(
                        dispatching,
                        dispatch_safety="dispatch_ambiguous",
                    ),
                )

                calls_before = tuple(runtime.calls)
                with self.assertRaisesRegex(HarnessLifecycleError, "resume"):
                    NativeRunRecoveryController(host, runtime).recover(TASK_ID)

                self.assertEqual(tuple(runtime.calls), calls_before)
                self.assertIn("workspace:oh5:g1", runtime.workspaces)
                with self.assertRaises(HarnessLifecycleError):
                    host.load_current_native_run_recovery(TASK_ID)
                current = HostHarnessRunStore(
                    host, host.load_current_assignment(TASK_ID)
                ).load_current_provider_call()
                self.assertEqual(current.record, unknown.record)
                validate_history(storage)

    def test_structured_failed_outcome_requires_resume_without_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(storage, clock, runtime)
                store, _, _, claimed = self._claim(host, committed)
                dispatching = store.mark_provider_call_dispatching(claimed)
                failed = store.fail_provider_call(
                    dispatching,
                    failure=_provider_failure(
                        dispatching,
                        dispatch_safety="provider_rejected",
                    ),
                )

                calls_before = tuple(runtime.calls)
                with self.assertRaisesRegex(HarnessLifecycleError, "resume"):
                    NativeRunRecoveryController(host, runtime).recover(TASK_ID)

                self.assertEqual(tuple(runtime.calls), calls_before)
                self.assertIn("workspace:oh5:g1", runtime.workspaces)
                with self.assertRaises(HarnessLifecycleError):
                    host.load_current_native_run_recovery(TASK_ID)
                current = HostHarnessRunStore(
                    host, host.load_current_assignment(TASK_ID)
                ).load_current_provider_call()
                self.assertEqual(current.record, failed.record)
                self.assertIsNotNone(current.failure)
                validate_history(storage)

    def test_repeated_dispatching_recovery_keeps_provider_blocker_and_head(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(storage, clock, runtime)
                store, _, _, claimed = self._claim(host, committed)
                dispatching = store.mark_provider_call_dispatching(claimed)

                first = NativeRunRecoveryController(host, runtime).recover(
                    TASK_ID
                )
                second = NativeRunRecoveryController(host, runtime).recover(
                    TASK_ID
                )

                self.assertIsNone(first.abandonment)
                self.assertIsNone(second.abandonment)
                self.assertEqual(first.recovery.assessment.sequence, 1)
                self.assertEqual(second.recovery.assessment.sequence, 2)
                self.assertEqual(
                    first.recovery.assessment.unresolved_unknowns,
                    second.recovery.assessment.unresolved_unknowns,
                )
                evidence = second.recovery.assessment.workspace_evidence
                provider = evidence["providerCallReconciliation"]
                assert isinstance(provider, dict)
                self.assertEqual(provider["status"], "dispatching")
                self.assertEqual(
                    provider["recordDigest"], dispatching.record.digest
                )
                current = HostHarnessRunStore(
                    host, host.load_current_assignment(TASK_ID)
                ).load_current_provider_call()
                self.assertEqual(current.record, dispatching.record)
                self.assertEqual(
                    storage.journal.get_task(TASK_ID).state,
                    TaskState.BLOCKED,
                )
                validate_history(storage)

    def test_unreadable_failure_outcome_records_conservative_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(storage, clock, runtime)
                store, _, _, claimed = self._claim(host, committed)
                dispatching = store.mark_provider_call_dispatching(claimed)
                failed = store.fail_provider_call(
                    dispatching,
                    failure=_provider_failure(
                        dispatching,
                        dispatch_safety="provider_rejected",
                    ),
                )
                failure_object_digest = failed.record.failure_object_digest
                assert failure_object_digest is not None
                (
                    Path(directory)
                    / "objects"
                    / f"{failure_object_digest[7:]}.json"
                ).unlink()

                result = NativeRunRecoveryController(host, runtime).recover(
                    TASK_ID
                )

                self.assertIsNone(result.abandonment)
                evidence = result.recovery.assessment.workspace_evidence
                provider = evidence["providerCallReconciliation"]
                assert isinstance(provider, dict)
                self.assertEqual(provider["status"], "unreadable")
                self.assertEqual(
                    evidence["providerCallUnresolvedUnknowns"],
                    ["active Provider Call state is unreadable"],
                )
                self.assertFalse(result.recovery.assessment.safe_to_abandon)
                self.assertEqual(
                    storage.journal.get_task(TASK_ID).state,
                    TaskState.BLOCKED,
                )

    def test_host_refuses_abandonment_if_provider_state_appears_after_assessment(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, _, _, _ = _assign(storage, clock, runtime)
                recovery = NativeRunRecoveryController(host, runtime).recover(
                    TASK_ID,
                    auto_abandon=False,
                ).recovery
                self.assertTrue(recovery.assessment.safe_to_abandon)

                current = host.load_current_assignment(TASK_ID)
                self._claim(host, current)
                refreshed = host.load_current_native_run_recovery(TASK_ID)
                with self.assertRaisesRegex(
                    HarnessLifecycleError, "Provider Call"
                ):
                    host.abandon_native_run(
                        refreshed,
                        reason_code=refreshed.assessment.trigger,
                    )
                with self.assertRaises(HarnessLifecycleError):
                    host.load_current_native_run_abandonment(TASK_ID)
                validate_history(storage)

    def test_invalid_trigger_is_rejected_before_runtime_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            runtime = _RecoveryRuntime()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, _, _, _ = _assign(storage, clock, runtime)
                calls_before = tuple(runtime.calls)

                with self.assertRaisesRegex(ValueError, "trigger"):
                    NativeRunRecoveryController(host, runtime).recover(
                        TASK_ID,
                        trigger="operator_recover",
                    )

                self.assertEqual(tuple(runtime.calls), calls_before)
                self.assertIn("workspace:oh5:g1", runtime.workspaces)
                with self.assertRaises(HarnessLifecycleError):
                    host.load_current_native_run_recovery(TASK_ID)

    def test_cli_recover_default_and_choices_use_protocol_triggers(self) -> None:
        parser = build_parser()
        args = parser.parse_args(("host", "recover", TASK_ID))
        self.assertEqual(args.trigger, "host_restart")
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    ("host", "recover", TASK_ID, "--trigger", "operator_recover")
                )


if __name__ == "__main__":
    unittest.main()
