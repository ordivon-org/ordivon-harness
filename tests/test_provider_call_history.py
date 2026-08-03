from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from anc_canonical import canonical_digest
from ordivon_host import (
    EventKind,
    HostExtensionPort,
    HostKernel,
    HostStorage,
    TaskState,
)
from ordivon_host.journal import JournalCorruption
from ordivon_host.objects import ObjectCorrupt, ObjectMissing, StoredObject
from test_ordivon_harness_oh5 import (
    TASK_ID,
    _RecoveryRuntime,
    _assign,
    _create_task,
)
from test_provider_call_recovery import (
    _MutableClock,
    _provider_failure,
    _provider_result,
    _provider_state,
)
from test_runner_r0_r1 import _plan, _turn

from ordivon_harness import (
    HarnessHost,
    HarnessProviderCallRequestMismatch,
    HarnessRunner,
)
from ordivon_harness.event_kinds import (
    HARNESS_PROVIDER_CALL_CLAIMED,
    HARNESS_PROVIDER_CALL_COMPLETED,
    HARNESS_PROVIDER_CALL_DISPATCHING,
    HARNESS_PROVIDER_CALL_FAILED,
    HARNESS_PROVIDER_CALL_SUPERSEDED,
)
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    HostHarnessRunStore,
    ScriptedTurnAdapter,
)
from ordivon_harness.protocol import (
    HarnessProviderCallRecord,
    HarnessProviderCallSource,
    HarnessProviderCallStatus,
    HarnessRunPauseReason,
)


def _claim(storage: HostStorage, clock: _MutableClock, *, ttl_ms: int = 1_000):
    host, committed, _, _ = _assign(storage, clock, _RecoveryRuntime())
    store = HostHarnessRunStore(host, committed)
    base_state = _provider_state()
    state = replace(
        base_state,
        remaining_budget={
            **base_state.remaining_budget,
            "modelRetries": 1,
        },
    )
    store.bind_state(state)
    arguments = {
        "source": store.assignment_provider_source(),
        "turn_id": "turn:provider-history:1",
        "turn_sequence": 1,
        "request_digest": canonical_digest({"request": "provider-history"}),
        "provider_request_digest": canonical_digest(
            {"providerRequest": "provider-history"}
        ),
        "adapter_id": "ordivon.provider-history-fixture.v1",
        "requested_model_id": ScriptedTurnAdapter.model_id,
        "holder_id": "holder:provider-history:first",
        "ttl_ms": ttl_ms,
    }
    return host, store, state, arguments, store.claim_provider_call(**arguments)


def _head_updates(
    record: HarnessProviderCallRecord,
    record_object: StoredObject,
) -> dict[str, object]:
    return {
        "activeHarnessProviderCallDigest": record.digest,
        "activeHarnessProviderCallObjectDigest": record_object.digest,
        "activeHarnessProviderCallId": record.provider_call_id,
        "activeHarnessProviderCallStatus": record.status.value,
        "activeHarnessProviderCallExpiresAtMs": record.expires_at_ms,
        "activeHarnessProviderCallGeneration": record.claim_generation,
    }


def _append_provider_record(
    storage: HostStorage,
    host,
    record: HarnessProviderCallRecord,
    *,
    event_kind,
    record_kind: str = "harness-provider-call-record",
    referenced_objects: tuple[StoredObject, ...] = (),
    updates: dict[str, object] | None = None,
) -> StoredObject:
    extension = HostExtensionPort(storage, host.kernel)
    record_object = extension.put_object(record.to_dict(), kind=record_kind)
    committed = host.load_current_assignment(TASK_ID)
    extension.append_preserving(
        task_id=TASK_ID,
        expected_revision=committed.task_revision,
        event_id=(
            "event:provider-history:"
            + canonical_digest(
                {
                    "record": record.digest,
                    "eventKind": event_kind.value,
                    "recordKind": record_kind,
                    "updates": updates,
                }
            )[7:31]
        ),
        kind=event_kind,
        updates=(
            _head_updates(record, record_object)
            if updates is None
            else updates
        ),
        remove_fields=(),
        referenced_objects=(record_object, *referenced_objects),
        label="Provider history corruption fixture",
    )
    return record_object


def _dispatch_record(
    claimed,
    *,
    previous_record_digest: str | None = None,
) -> HarnessProviderCallRecord:
    return replace(
        claimed.record,
        record_id="harness-provider-call-record:provider-history:dispatching",
        status=HarnessProviderCallStatus.DISPATCHING,
        previous_record_digest=(
            claimed.record.digest
            if previous_record_digest is None
            else previous_record_digest
        ),
        recorded_at_ms=claimed.record.recorded_at_ms + 1,
    )


class ProviderCallHistoryTests(unittest.TestCase):
    def test_old_history_without_provider_events_remains_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                _assign(storage, clock, _RecoveryRuntime())

                validation = validate_history(storage)

                self.assertEqual(validation.provider_semantic_link_checks, 0)
                self.assertEqual(
                    validation.to_dict()["providerSemanticLinkChecks"],
                    0,
                )

    def test_every_provider_lifecycle_event_is_semantically_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, store, state, arguments, claimed = _claim(storage, clock)
                dispatching = store.mark_provider_call_dispatching(claimed)
                store.complete_provider_call(dispatching, _provider_result())
                completed_validation = validate_history(storage)
                self.assertGreater(
                    completed_validation.provider_semantic_link_checks,
                    0,
                )
                self.assertGreaterEqual(
                    completed_validation.semantic_link_checks,
                    completed_validation.provider_semantic_link_checks,
                )

                store.bind_state(state)
                store.record_pause(HarnessRunPauseReason.NEEDS_INPUT)
                snapshot = store.load_current_snapshot()
                store.claim_provider_call(
                    **{
                        **arguments,
                        "source": store.snapshot_provider_source(snapshot),
                        "holder_id": "holder:provider-history:after-clear",
                    }
                )
                self.assertGreater(
                    validate_history(storage).provider_semantic_link_checks,
                    completed_validation.provider_semantic_link_checks,
                )

        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                _, store, state, _, claimed = _claim(storage, clock)
                dispatching = store.mark_provider_call_dispatching(claimed)
                failed = store.fail_provider_call(
                    dispatching,
                    failure=_provider_failure(
                        dispatching,
                        dispatch_safety="pre_dispatch_safe",
                    ),
                )
                store.bind_state(
                    replace(
                        state,
                        remaining_budget={
                            **state.remaining_budget,
                            "modelRetries": 0,
                        },
                    )
                )
                retry = store.retry_failed_provider_call(
                    failed,
                    holder_id="holder:provider-history:retry",
                    ttl_ms=1_000,
                )
                retry_dispatch = store.mark_provider_call_dispatching(retry)
                store.fail_provider_call(
                    retry_dispatch,
                    failure=_provider_failure(
                        retry_dispatch,
                        dispatch_safety="dispatch_ambiguous",
                    ),
                )
                self.assertGreater(
                    validate_history(storage).provider_semantic_link_checks,
                    0,
                )

        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, _, state, arguments, claimed = _claim(
                    storage,
                    clock,
                    ttl_ms=10,
                )
                clock.value = claimed.record.expires_at_ms + 1
                store = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                )
                store.bind_state(state)
                store.claim_provider_call(
                    **{
                        **arguments,
                        "holder_id": "holder:provider-history:reclaim",
                    }
                )
                self.assertGreater(
                    validate_history(storage).provider_semantic_link_checks,
                    0,
                )

    def test_missing_completed_result_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                _, store, _, _, claimed = _claim(storage, clock)
                dispatching = store.mark_provider_call_dispatching(claimed)
                completed = store.complete_provider_call(
                    dispatching,
                    _provider_result(),
                )
                assert completed.record.result_object_digest is not None
                (
                    Path(directory)
                    / "objects"
                    / f"{completed.record.result_object_digest[7:]}.json"
                ).unlink()

                with self.assertRaises(ObjectMissing):
                    validate_history(storage)

    def test_wrong_record_kind_tampered_head_and_broken_chain_fail_closed(
        self,
    ) -> None:
        cases = ("wrong-kind", "head-digest", "broken-chain")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                clock = _MutableClock()
                with HostStorage(directory) as storage:
                    _create_task(storage, clock)
                    host, _, _, _, claimed = _claim(storage, clock)
                    previous_digest = (
                        canonical_digest({"broken": "predecessor"})
                        if case == "broken-chain"
                        else None
                    )
                    dispatching = _dispatch_record(
                        claimed,
                        previous_record_digest=previous_digest,
                    )
                    state_object = storage.objects.inspect(
                        dispatching.state_object_digest
                    )
                    record_kind = (
                        "not-a-provider-call-record"
                        if case == "wrong-kind"
                        else "harness-provider-call-record"
                    )
                    if case == "head-digest":
                        extension = HostExtensionPort(storage, host.kernel)
                        record_object = extension.put_object(
                            dispatching.to_dict(),
                            kind=record_kind,
                        )
                        updates = _head_updates(dispatching, record_object)
                        updates["activeHarnessProviderCallDigest"] = canonical_digest(
                            {"tampered": "head"}
                        )
                        _append_provider_record(
                            storage,
                            host,
                            dispatching,
                            event_kind=HARNESS_PROVIDER_CALL_DISPATCHING,
                            record_kind=record_kind,
                            referenced_objects=(state_object,),
                            updates=updates,
                        )
                    else:
                        _append_provider_record(
                            storage,
                            host,
                            dispatching,
                            event_kind=HARNESS_PROVIDER_CALL_DISPATCHING,
                            record_kind=record_kind,
                            referenced_objects=(state_object,),
                        )

                    expected = (
                        ObjectCorrupt
                        if case == "wrong-kind"
                        else JournalCorruption
                    )
                    with self.assertRaises(expected):
                        validate_history(storage)

    def test_supersession_cannot_replace_or_revive_durable_state(self) -> None:
        for mode in ("expired-claim", "safe-retry"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                clock = _MutableClock()
                with HostStorage(directory) as storage:
                    _create_task(storage, clock)
                    host, store, state, _, claimed = _claim(
                        storage,
                        clock,
                        ttl_ms=10,
                    )
                    if mode == "expired-claim":
                        previous = claimed
                        clock.value = claimed.record.expires_at_ms + 1
                        changed_state = replace(
                            state,
                            remaining_budget={
                                **state.remaining_budget,
                                "wallTimeMs": (
                                    int(state.remaining_budget["wallTimeMs"]) + 1
                                ),
                            },
                        )
                        state_object = HostExtensionPort(
                            storage,
                            host.kernel,
                        ).put_object(
                            changed_state.to_dict(store.harness_run_id),
                            kind="harness-run-state",
                        )
                    else:
                        dispatching = store.mark_provider_call_dispatching(
                            claimed
                        )
                        previous = store.fail_provider_call(
                            dispatching,
                            failure=_provider_failure(
                                dispatching,
                                dispatch_safety="pre_dispatch_safe",
                            ),
                        )
                        state_object = previous.state_object
                    invalid = replace(
                        previous.record,
                        record_id=(
                            "harness-provider-call-record:"
                            f"provider-history:invalid-{mode}"
                        ),
                        holder_id="holder:provider-history:replacement",
                        claim_generation=previous.record.claim_generation + 1,
                        status=HarnessProviderCallStatus.CLAIMED,
                        state_object_digest=state_object.digest,
                        result_digest=None,
                        result_object_digest=None,
                        failure_digest=None,
                        failure_object_digest=None,
                        previous_record_digest=previous.record.digest,
                        issued_at_ms=clock.value,
                        expires_at_ms=clock.value + 1_000,
                        recorded_at_ms=clock.value,
                    )
                    _append_provider_record(
                        storage,
                        host,
                        invalid,
                        event_kind=HARNESS_PROVIDER_CALL_SUPERSEDED,
                        referenced_objects=(state_object,),
                    )

                    with self.assertRaisesRegex(
                        JournalCorruption,
                        "supersession",
                    ):
                        validate_history(storage)

    def test_expired_claim_may_advance_only_active_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                _, store, state, arguments, claimed = _claim(
                    storage,
                    clock,
                    ttl_ms=10,
                )
                advanced = replace(
                    state,
                    active_elapsed_ms=1,
                    remaining_budget={
                        **state.remaining_budget,
                        "wallTimeMs": (
                            int(state.remaining_budget["wallTimeMs"]) - 1
                        ),
                    },
                )
                store.bind_state(advanced)
                clock.value = claimed.record.expires_at_ms + 1

                superseded = store.claim_provider_call(
                    **{
                        **arguments,
                        "holder_id": "holder:provider-history:replacement",
                    }
                )

                self.assertEqual(superseded.record.claim_generation, 2)
                self.assertNotEqual(
                    superseded.record.state_object_digest,
                    claimed.record.state_object_digest,
                )
                self.assertEqual(superseded.state, advanced)
                validate_history(storage)

    def test_safe_retry_write_rejects_non_retry_state_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                _, store, _, _, claimed = _claim(storage, clock)
                dispatching = store.mark_provider_call_dispatching(claimed)
                failed = store.fail_provider_call(
                    dispatching,
                    failure=_provider_failure(
                        dispatching,
                        dispatch_safety="pre_dispatch_safe",
                    ),
                )
                tampered = replace(
                    failed.state,
                    messages=failed.state.messages
                    + ({"role": "user", "content": "unauthorized retry mutation"},),
                    remaining_budget={
                        **failed.state.remaining_budget,
                        "modelRetries": (
                            int(failed.state.remaining_budget["modelRetries"]) - 1
                        ),
                    },
                )
                store.bind_state(tampered)

                with self.assertRaisesRegex(
                    HarnessProviderCallRequestMismatch,
                    "outside retry accounting",
                ):
                    store.retry_failed_provider_call(
                        failed,
                        holder_id="holder:provider-history:retry",
                        ttl_ms=1_000,
                    )

    def test_history_rejects_inconsistent_v2_active_time_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _RecoveryRuntime()
                paused = HarnessRunner(
                    HarnessHost(storage, clock_ms=clock),
                    runtime=runtime,
                    adapter=ScriptedTurnAdapter(
                        (
                            _turn(
                                "provider-history-time-budget",
                                conclusion=AgentRunConclusion(
                                    status="needs_input",
                                    summary="Pause before history tampering.",
                                ),
                            ),
                        )
                    ),
                    monotonic_ms=_MutableClock(0),
                ).run(_plan())
                self.assertTrue(paused.paused)

                host = HarnessHost(storage, clock_ms=clock)
                committed = host.load_current_assignment(TASK_ID)
                store = HostHarnessRunStore(host, committed)
                retained = store.load_current_snapshot()
                store.bind_state(retained.state)
                claimed = store.claim_provider_call(
                    source=store.snapshot_provider_source(retained),
                    turn_id="turn:provider-history-time-budget:2",
                    turn_sequence=2,
                    request_digest=canonical_digest(
                        {"request": "provider-history-time-budget"}
                    ),
                    provider_request_digest=canonical_digest(
                        {"providerRequest": "provider-history-time-budget"}
                    ),
                    adapter_id="ordivon.provider-history-time-budget.v1",
                    requested_model_id=ScriptedTurnAdapter.model_id,
                    holder_id="holder:provider-history-time-budget:first",
                    ttl_ms=10,
                )
                assert claimed.state.active_elapsed_ms is not None
                inconsistent = replace(
                    claimed.state,
                    active_elapsed_ms=claimed.state.active_elapsed_ms + 1,
                )
                state_object = HostExtensionPort(
                    storage,
                    host.kernel,
                ).put_object(
                    inconsistent.to_dict(store.harness_run_id),
                    kind="harness-run-state",
                )
                clock.value = claimed.record.expires_at_ms + 1
                invalid = replace(
                    claimed.record,
                    record_id=(
                        "harness-provider-call-record:"
                        "provider-history:invalid-active-time"
                    ),
                    holder_id="holder:provider-history-time-budget:replacement",
                    claim_generation=claimed.record.claim_generation + 1,
                    state_object_digest=state_object.digest,
                    previous_record_digest=claimed.record.digest,
                    issued_at_ms=clock.value,
                    expires_at_ms=clock.value + 1_000,
                    recorded_at_ms=clock.value,
                )
                _append_provider_record(
                    storage,
                    host,
                    invalid,
                    event_kind=HARNESS_PROVIDER_CALL_SUPERSEDED,
                    referenced_objects=(state_object,),
                )

                with self.assertRaisesRegex(
                    JournalCorruption,
                    "saved Run state",
                ):
                    validate_history(storage)

    def test_dispatching_head_cannot_be_cleared_by_a_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                _, store, _, _, claimed = _claim(storage, clock)
                store.mark_provider_call_dispatching(claimed)
                store.record_pause(HarnessRunPauseReason.NEEDS_INPUT)

                with self.assertRaisesRegex(
                    JournalCorruption,
                    "illegally cleared",
                ):
                    validate_history(storage)

    def test_nested_provider_objects_must_be_admitted(self) -> None:
        for nested in ("state", "result", "failure"):
            with self.subTest(nested=nested), tempfile.TemporaryDirectory() as directory:
                clock = _MutableClock()
                with HostStorage(directory) as storage:
                    _create_task(storage, clock)
                    if nested == "state":
                        host, committed, _, _ = _assign(
                            storage,
                            clock,
                            _RecoveryRuntime(),
                        )
                        extension = HostExtensionPort(storage, host.kernel)
                        state = _provider_state()
                        state_object = extension.put_object(
                            state.to_dict(
                                committed.native_run_contract.harness_run_id
                            ),
                            kind="harness-run-state",
                        )
                        source = HostHarnessRunStore(
                            host,
                            committed,
                        ).assignment_provider_source()
                        record = HarnessProviderCallRecord(
                            record_id=(
                                "harness-provider-call-record:"
                                "provider-history:unadmitted-state"
                            ),
                            provider_call_id="provider-call:provider-history:state",
                            task_id=TASK_ID,
                            harness_run_id=(
                                committed.native_run_contract.harness_run_id
                            ),
                            assignment_id=committed.assignment.assignment_id,
                            assignment_generation=committed.assignment.generation,
                            assignment_digest=committed.assignment.digest,
                            source_kind=HarnessProviderCallSource.ASSIGNMENT,
                            source_digest=source.digest,
                            source_object_digest=source.object_digest,
                            state_object_digest=state_object.digest,
                            turn_id="turn:provider-history:1",
                            turn_sequence=1,
                            request_digest=canonical_digest({"request": "state"}),
                            provider_request_digest=canonical_digest(
                                {"providerRequest": "state"}
                            ),
                            adapter_id="ordivon.provider-history-fixture.v1",
                            requested_model_id=ScriptedTurnAdapter.model_id,
                            holder_id="holder:provider-history:state",
                            claim_generation=1,
                            status=HarnessProviderCallStatus.CLAIMED,
                            result_digest=None,
                            result_object_digest=None,
                            failure_digest=None,
                            failure_object_digest=None,
                            previous_record_digest=None,
                            issued_at_ms=clock.value,
                            expires_at_ms=clock.value + 1_000,
                            recorded_at_ms=clock.value,
                        )
                        _append_provider_record(
                            storage,
                            host,
                            record,
                            event_kind=HARNESS_PROVIDER_CALL_CLAIMED,
                        )
                    else:
                        host, store, _, _, claimed = _claim(storage, clock)
                        dispatching = store.mark_provider_call_dispatching(claimed)
                        extension = HostExtensionPort(storage, host.kernel)
                        if nested == "result":
                            result = _provider_result()
                            outcome_object = extension.put_object(
                                result.to_dict(),
                                kind="agent-turn-result",
                            )
                            record = replace(
                                dispatching.record,
                                record_id=(
                                    "harness-provider-call-record:"
                                    "provider-history:unadmitted-result"
                                ),
                                status=HarnessProviderCallStatus.COMPLETED,
                                result_digest=result.digest,
                                result_object_digest=outcome_object.digest,
                                previous_record_digest=dispatching.record.digest,
                                recorded_at_ms=(
                                    dispatching.record.recorded_at_ms + 1
                                ),
                            )
                            event_kind = HARNESS_PROVIDER_CALL_COMPLETED
                        else:
                            failure = _provider_failure(
                                dispatching,
                                dispatch_safety="provider_rejected",
                            )
                            outcome_object = extension.put_object(
                                failure.to_dict(),
                                kind="harness-provider-call-failure",
                            )
                            record = replace(
                                dispatching.record,
                                record_id=(
                                    "harness-provider-call-record:"
                                    "provider-history:unadmitted-failure"
                                ),
                                status=HarnessProviderCallStatus.FAILED,
                                failure_digest=failure.digest,
                                failure_object_digest=outcome_object.digest,
                                previous_record_digest=dispatching.record.digest,
                                recorded_at_ms=(
                                    dispatching.record.recorded_at_ms + 1
                                ),
                            )
                            event_kind = HARNESS_PROVIDER_CALL_FAILED
                        _append_provider_record(
                            storage,
                            host,
                            record,
                            event_kind=event_kind,
                            referenced_objects=(
                                storage.objects.inspect(
                                    record.state_object_digest
                                ),
                            ),
                        )

                    with self.assertRaisesRegex(
                        JournalCorruption,
                        f"Provider Call {nested}",
                    ):
                        validate_history(storage)

    def test_same_millisecond_later_event_cannot_repair_provider_admission(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                _, store, _, _, claimed = _claim(storage, clock)
                dispatching = store.mark_provider_call_dispatching(claimed)
                completed = store.complete_provider_call(
                    dispatching,
                    _provider_result(),
                )
                result_digest = completed.record.result_object_digest
                assert result_digest is not None
                completed_event = storage.journal.connection.execute(
                    "SELECT sequence, event_id, recorded_at_ms FROM events "
                    "WHERE event_kind = ? ORDER BY sequence DESC LIMIT 1",
                    (HARNESS_PROVIDER_CALL_COMPLETED.value,),
                ).fetchone()
                assert completed_event is not None
                storage.journal.connection.execute(
                    "DELETE FROM event_object_refs WHERE event_id = ? "
                    "AND digest = ?",
                    (completed_event["event_id"], result_digest),
                )

                same_ms = int(completed_event["recorded_at_ms"])
                HostKernel(
                    storage,
                    clock_ms=lambda: same_ms,
                    owner_id="host:provider-history:same-ms",
                ).create_task(
                    event_id="event:provider-history:same-ms:later",
                    kind=EventKind.TASK_CREATED,
                    task_id="task:provider-history:same-ms:later",
                    goal_id="goal:provider-history:same-ms",
                    payload={"workloadId": "provider-history-same-ms"},
                    state=TaskState.READY,
                    frontier=("node:provider-history:same-ms",),
                    referenced_objects=(storage.objects.inspect(result_digest),),
                )
                later = storage.journal.connection.execute(
                    "SELECT sequence, recorded_at_ms FROM events "
                    "WHERE event_id = ?",
                    ("event:provider-history:same-ms:later",),
                ).fetchone()
                assert later is not None
                self.assertGreater(
                    int(later["sequence"]),
                    int(completed_event["sequence"]),
                )
                self.assertEqual(int(later["recorded_at_ms"]), same_ms)
                self.assertIn(
                    result_digest,
                    {
                        item.digest
                        for item in storage.journal.event_object_references(
                            "event:provider-history:same-ms:later"
                        )
                    },
                )

                with self.assertRaisesRegex(
                    JournalCorruption,
                    "Provider Call result is not admitted by its Event",
                ):
                    validate_history(storage)


if __name__ == "__main__":
    unittest.main()
