from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import time
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.core_contracts import (
    HarnessBoundReference,
    HarnessRunContract,
)
from ordivon_harness.ordivon.continuity_records import (
    HarnessProviderCallRecordV2,
    HarnessProviderCallRecordV4,
)
from ordivon_harness.ordivon.model import AgentRunConclusion, AgentTurnResult
from ordivon_harness.ordivon.run_store_port import (
    HarnessProviderCallClaimHeld,
    HarnessProviderCallRecoveryRequired,
    HarnessProviderCallRequestMismatch,
)
from ordivon_harness.ordivon.sqlite_run_store import (
    SQLiteHarnessRunContinuityStore,
)
from ordivon_harness.protocol import (
    HarnessProviderCallFailureReceipt,
    HarnessProviderCallStatus,
)
from ordivon_harness.run_state import HarnessRunState
from ordivon_harness.sqlite_store import SQLiteHarnessStore

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64


class MutableClock:
    def __init__(self, value: int = 1_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value

    def advance(self, milliseconds: int = 1) -> None:
        self.value += milliseconds


def contract() -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id="harness-run:p0-provider-001",
        harness_implementation_id="ordivon-harness@0.7.0-dev",
        caller_id="caller:provider-store-test",
        caller_run_ref="trial:p0-provider-001",
        objective_ref=HarnessBoundReference("objective:p0-provider-001", "objective", DIGEST_A),
        context_refs=(HarnessBoundReference("context:p0-provider-001", "context", DIGEST_B),),
        provider_id="provider:scripted",
        adapter_id="adapter:scripted-v1",
        requested_model_id="model:scripted",
        tool_catalog_digest=DIGEST_C,
        tool_grant_digest=DIGEST_D,
        budget={
            "maxModelCalls": 4,
            "maxToolCalls": 4,
            "maxObservationBytes": 65_536,
            "maxWallTimeMs": 30_000,
            "maxModelRetries": 2,
        },
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            "system-manifest:p0-provider-001", "system-manifest", DIGEST_A
        ),
        created_at_ms=1_000,
    )


def state(
    *,
    elapsed: int = 0,
    wall_time_ms: int = 30_000,
    retries: int = 2,
) -> HarnessRunState:
    return HarnessRunState(
        messages=({"role": "user", "content": "provider continuity"},),
        observations=(),
        remaining_budget={
            "modelCalls": 4,
            "toolCalls": 4,
            "observationBytes": 65_536,
            "wallTimeMs": wall_time_ms,
            "modelRetries": retries,
        },
        requested_model_id="model:scripted",
        effective_model_id=None,
        active_elapsed_ms=elapsed,
    )


def result(suffix: str = "completed") -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:p0-provider:{suffix}",
        model_id="model:scripted",
        content=None,
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Independent Provider Call completed.",
        ),
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"result": suffix}),
    )


def failure(
    provider_call_id: str,
    request_digest: str,
    provider_request_digest: str,
    *,
    safety: str,
    suffix: str,
) -> HarnessProviderCallFailureReceipt:
    return HarnessProviderCallFailureReceipt(
        provider_call_id=provider_call_id,
        request_digest=request_digest,
        provider_request_digest=provider_request_digest,
        failure_code="provider_transport_failed",
        dispatch_safety=safety,
        detail=f"fixture Provider failure: {suffix}",
    )


class SQLiteHarnessRunContinuityProviderTests(unittest.TestCase):
    def prepare(
        self,
        root: Path,
        clock: MutableClock,
    ) -> tuple[SQLiteHarnessStore, SQLiteHarnessRunContinuityStore]:
        store = SQLiteHarnessStore.initialize(root)
        value = contract()
        store.create_run(value)
        provider = SQLiteHarnessRunContinuityStore(
            store,
            value,
            clock_ms=clock,
        )
        provider.bind_state(state())
        return store, provider

    @staticmethod
    def claim(provider: SQLiteHarnessRunContinuityStore, *, holder: str = "holder:first"):
        source = provider.assignment_provider_source()
        return provider.claim_provider_call(
            source=source,
            turn_id="turn:p0-provider:1",
            turn_sequence=1,
            request_digest=canonical_digest({"request": 1}),
            provider_request_digest=canonical_digest({"providerRequest": 1}),
            adapter_id="adapter:scripted-v1",
            requested_model_id="model:scripted",
            holder_id=holder,
            ttl_ms=10,
        )

    def test_claim_dispatch_complete_reopens_from_independent_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, provider = self.prepare(root, clock)
            claimed = self.claim(provider)
            self.assertIsInstance(claimed.record, HarnessProviderCallRecordV2)
            self.assertEqual(claimed.record.status, HarnessProviderCallStatus.CLAIMED)
            self.assertEqual(self.claim(provider), claimed)

            clock.advance()
            dispatching = provider.mark_provider_call_dispatching(claimed)
            self.assertEqual(dispatching.record.status, HarnessProviderCallStatus.DISPATCHING)
            provider.bind_state(state(elapsed=10, wall_time_ms=29_990))
            clock.advance()
            completed = provider.complete_provider_call(dispatching, result())
            self.assertEqual(completed.record.status, HarnessProviderCallStatus.COMPLETED)
            self.assertIsInstance(completed.record, HarnessProviderCallRecordV4)
            self.assertEqual(completed.record.result_digest, result().digest)
            self.assertIsNone(completed.record.result_object_digest)
            self.assertIsNone(completed.result)
            self.assertIsNone(completed.result_object)
            self.assertEqual(provider.complete_provider_call(completed, result()), completed)
            revision = provider.caller_revision
            store.close()

            with SQLiteHarnessStore(root) as reopened:
                fresh = SQLiteHarnessRunContinuityStore(
                    reopened,
                    contract(),
                    clock_ms=clock,
                )
                retained = fresh.load_current_provider_call()
                self.assertEqual(retained.record.status, HarnessProviderCallStatus.COMPLETED)
                self.assertIsInstance(retained.record, HarnessProviderCallRecordV4)
                self.assertEqual(retained.record.result_digest, result().digest)
                self.assertIsNone(retained.result)
                self.assertIsNone(retained.result_object)
                self.assertEqual(fresh.caller_revision, revision)
                self.assertEqual(
                    [
                        event.event_kind
                        for event in reopened.list_run_events(contract().harness_run_id)
                    ],
                    [
                        "harness.run-created",
                        "harness.provider-call-claimed",
                        "harness.provider-call-dispatching",
                        "harness.provider-call-completed",
                    ],
                )
                self.assertTrue(reopened.doctor(full=True)["healthy"])

    def test_live_claim_excludes_other_holder_and_expiry_allows_reclaim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, first = self.prepare(root, clock)
            claimed = self.claim(first)
            second = SQLiteHarnessRunContinuityStore(
                store,
                contract(),
                clock_ms=clock,
            )
            second.bind_state(state())
            with self.assertRaises(HarnessProviderCallClaimHeld):
                self.claim(second, holder="holder:second")

            clock.value = claimed.record.expires_at_ms + 1
            reclaimed = self.claim(second, holder="holder:second")
            self.assertEqual(reclaimed.record.claim_generation, 2)
            self.assertEqual(reclaimed.record.holder_id, "holder:second")
            store.close()

    def test_dispatching_call_requires_recovery_instead_of_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, first = self.prepare(root, clock)
            claimed = self.claim(first)
            first.mark_provider_call_dispatching(claimed)
            fresh = SQLiteHarnessRunContinuityStore(
                store,
                contract(),
                clock_ms=clock,
            )
            fresh.bind_state(state())
            with self.assertRaises(HarnessProviderCallRecoveryRequired):
                self.claim(fresh)
            store.close()

    def test_dispatching_replay_does_not_take_run_lease_from_outcome_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, winner = self.prepare(root, clock)
            claimed = self.claim(winner)
            dispatching = winner.mark_provider_call_dispatching(claimed)
            contender = SQLiteHarnessRunContinuityStore(
                store,
                contract(),
                clock_ms=clock,
            )
            contender.bind_state(state())
            lease_acquisitions: list[str] = []
            original_acquire = store.acquire_run_lease

            def tracked_acquire(*args, **kwargs):
                lease_acquisitions.append(kwargs["owner_id"])
                return original_acquire(*args, **kwargs)

            store.acquire_run_lease = tracked_acquire
            try:
                with self.assertRaises(HarnessProviderCallRecoveryRequired):
                    self.claim(contender, holder="holder:contender")
                self.assertEqual(lease_acquisitions, [])
            finally:
                store.acquire_run_lease = original_acquire

            winner.bind_state(state(elapsed=10, wall_time_ms=29_990))
            completed = winner.complete_provider_call(dispatching, result())
            self.assertEqual(completed.record.status, HarnessProviderCallStatus.COMPLETED)
            store.close()

    def test_dispatched_outcome_waits_for_transient_run_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, winner = self.prepare(root, clock)
            claimed = self.claim(winner)
            dispatching = winner.mark_provider_call_dispatching(claimed)
            store.close()

            blocker_store = SQLiteHarnessStore(root)
            blocking_lease = blocker_store.acquire_run_lease(
                contract().harness_run_id,
                owner_id="test:transient-contender",
                ttl_ms=30_000,
                now_ms=clock(),
            )

            def commit_outcome():
                with SQLiteHarnessStore(root) as outcome_store:
                    outcome = SQLiteHarnessRunContinuityStore(
                        outcome_store,
                        contract(),
                        clock_ms=clock,
                    )
                    outcome.bind_state(state(elapsed=10, wall_time_ms=29_990))
                    return outcome.complete_provider_call(dispatching, result())

            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(commit_outcome)
                    time.sleep(0.02)
                    self.assertFalse(future.done())
                    blocker_store.release_run_lease(blocking_lease)
                    completed = future.result(timeout=2.0)
                self.assertEqual(
                    completed.record.status,
                    HarnessProviderCallStatus.COMPLETED,
                )
            finally:
                blocker_store.release_run_lease(blocking_lease)
                blocker_store.close()

    def test_claim_owner_waits_for_transient_run_lease_before_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, winner = self.prepare(root, clock)
            claimed = self.claim(winner)
            store.close()

            blocker_store = SQLiteHarnessStore(root)
            blocking_lease = blocker_store.acquire_run_lease(
                contract().harness_run_id,
                owner_id="test:transient-pre-dispatch-contender",
                ttl_ms=30_000,
                now_ms=clock(),
            )

            def admit_dispatch():
                with SQLiteHarnessStore(root) as dispatch_store:
                    dispatch = SQLiteHarnessRunContinuityStore(
                        dispatch_store,
                        contract(),
                        clock_ms=clock,
                    )
                    dispatch.bind_state(state())
                    return dispatch.mark_provider_call_dispatching(claimed)

            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(admit_dispatch)
                    time.sleep(0.02)
                    self.assertFalse(future.done())
                    blocker_store.release_run_lease(blocking_lease)
                    dispatching = future.result(timeout=2.0)
                self.assertEqual(
                    dispatching.record.status,
                    HarnessProviderCallStatus.DISPATCHING,
                )
            finally:
                blocker_store.release_run_lease(blocking_lease)
                blocker_store.close()

    def test_safe_claim_failure_can_retry_only_after_budget_consumption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, provider = self.prepare(root, clock)
            claimed = self.claim(provider)
            safe = failure(
                claimed.record.provider_call_id,
                claimed.record.request_digest,
                claimed.record.provider_request_digest,
                safety="pre_dispatch_safe",
                suffix="safe",
            )
            provider.bind_state(state(elapsed=5, wall_time_ms=29_995))
            failed = provider.fail_claimed_provider_call(claimed, failure=safe)
            self.assertEqual(failed.record.status, HarnessProviderCallStatus.FAILED)

            provider.bind_state(state(elapsed=6, wall_time_ms=29_994, retries=2))
            with self.assertRaisesRegex(
                HarnessProviderCallRequestMismatch, "consume exactly one retry"
            ):
                provider.retry_failed_provider_call(
                    failed,
                    holder_id="holder:retry",
                    ttl_ms=10,
                )
            provider.bind_state(state(elapsed=6, wall_time_ms=29_994, retries=1))
            retried = provider.retry_failed_provider_call(
                failed,
                holder_id="holder:retry",
                ttl_ms=10,
            )
            self.assertEqual(retried.record.status, HarnessProviderCallStatus.CLAIMED)
            self.assertEqual(retried.record.claim_generation, 2)
            store.close()

    def test_ambiguous_dispatched_failure_becomes_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, provider = self.prepare(root, clock)
            claimed = self.claim(provider)
            dispatching = provider.mark_provider_call_dispatching(claimed)
            ambiguous = failure(
                dispatching.record.provider_call_id,
                dispatching.record.request_digest,
                dispatching.record.provider_request_digest,
                safety="dispatch_ambiguous",
                suffix="ambiguous",
            )
            provider.bind_state(state(elapsed=5, wall_time_ms=29_995))
            unknown = provider.fail_provider_call(dispatching, failure=ambiguous)
            self.assertEqual(unknown.record.status, HarnessProviderCallStatus.UNKNOWN)
            self.assertTrue(provider.provider_outcome_requires_resume)
            fresh = SQLiteHarnessRunContinuityStore(
                store,
                contract(),
                clock_ms=clock,
            )
            fresh.bind_state(state(elapsed=5, wall_time_ms=29_995))
            retained = self.claim(fresh)
            self.assertEqual(retained.record.status, HarnessProviderCallStatus.UNKNOWN)
            self.assertTrue(fresh.provider_outcome_requires_resume)
            store.close()

    def test_stale_completion_loser_does_not_write_result_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, winner = self.prepare(root, clock)
            claimed = self.claim(winner)
            dispatching = winner.mark_provider_call_dispatching(claimed)
            loser = SQLiteHarnessRunContinuityStore(
                store,
                contract(),
                clock_ms=clock,
            )
            loser.bind_state(state(elapsed=10, wall_time_ms=29_990))
            winner.bind_state(state(elapsed=10, wall_time_ms=29_990))
            original = loser._require_current_provider_call

            def interleave(expected):
                current = original(expected)
                winner.complete_provider_call(dispatching, result("winner"))
                return current

            loser._require_current_provider_call = interleave
            losing_result = result("loser")
            envelope_digest = canonical_digest(
                {
                    "schemaVersion": 1,
                    "kind": "agent-turn-result",
                    "payload": losing_result.to_dict(),
                }
            )
            object_path = root / "objects" / f"{envelope_digest[7:]}.json"
            with self.assertRaises(HarnessProviderCallRequestMismatch):
                loser.complete_provider_call(dispatching, losing_result)
            self.assertFalse(object_path.exists())
            retained = winner.load_current_provider_call()
            self.assertIsInstance(retained.record, HarnessProviderCallRecordV4)
            self.assertEqual(retained.record.result_digest, result("winner").digest)
            self.assertIsNone(retained.result)
            self.assertIsNone(retained.result_object)
            store.close()

    def test_provider_identity_rejects_different_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, provider = self.prepare(root, clock)
            self.claim(provider)
            source = provider.assignment_provider_source()
            with self.assertRaises(HarnessProviderCallRequestMismatch):
                provider.claim_provider_call(
                    source=source,
                    turn_id="turn:p0-provider:1",
                    turn_sequence=1,
                    request_digest=canonical_digest({"request": "different"}),
                    provider_request_digest=canonical_digest({"providerRequest": 1}),
                    adapter_id="adapter:scripted-v1",
                    requested_model_id="model:scripted",
                    holder_id="holder:first",
                    ttl_ms=10,
                )
            store.close()


if __name__ == "__main__":
    unittest.main()
