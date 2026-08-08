from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

from ordivon_harness.ordivon.loop import OrdivonAgentLoop
from ordivon_harness.core_contracts import HarnessPrivacyPolicy
from ordivon_harness.ordivon.model import ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_agent_bridge import SQLiteHarnessAgentBridge
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.projected_no_tool import WorkingViewNoToolTurnRunner
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.store import HarnessEventAdmission
from ordivon_harness.working_view import (
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingViewSource,
    compile_working_view,
)

from tests.test_p0_sqlite_agent_loop import (
    FixedClock,
    budget,
    completed_result,
    contract,
)


def _private_content_contract(suffix: str):
    return replace(
        contract(suffix),
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=False,
        ),
    )


def _crash_after_projected_provider_completion(root_text: str) -> None:
    root = Path(root_text)
    clock = FixedClock()
    run_contract = _private_content_contract("pc11-projected-crash")
    with SQLiteHarnessStore.initialize(root) as store:
        store.create_run(run_contract)
        continuity = SQLiteHarnessRunContinuityStore(
            store, run_contract, clock_ms=clock
        )
        source = HarnessWorkingViewSource(
            logical_ref="source://pc11/current",
            logical_generation="git:pc11-a",
            messages=(
                {"role": "system", "content": "Use the selected source."},
                {"role": "user", "content": "TOKEN=ALPHA"},
            ),
        )
        stored = continuity.store_working_view_source(source)
        initial = HarnessWorkingSetSpec.initial(
            "working-attempt:crash-1",
            pins=(
                HarnessWorkingSetPin(
                    slot="primary",
                    logical_ref=source.logical_ref,
                    logical_generation=source.logical_generation,
                    resolved_digest=stored.digest,
                ),
            ),
        )
        continuity.record_working_set(initial)
        committed = initial.commit("selected source is enough for this attempt")
        adapter = ScriptedTurnAdapter((completed_result("pc11-projected-crash"),))
        runner = WorkingViewNoToolTurnRunner(
            store,
            run_contract,
            continuity,
            adapter,
            budget=budget(),
            clock_ms=clock,
            monotonic_ms=clock,
        )
        execution = runner.run(committed)
        retained = continuity.load_current_provider_call()
        handoff = {
            "workingSetDigest": committed.digest,
            "workingViewDigest": execution.working_view.digest,
            "requestDispatchDigest": execution.request.dispatch_digest,
            "requestObjectDigest": retained.request_object.digest,
            "physicalProviderCalls": len(adapter.requests),
            "runStateMessages": len(retained.state.messages),
            "requestMessages": len(execution.request.messages),
        }
        path = root.parent / "pc11-handoff.json"
        with path.open("w") as stream:
            json.dump(handoff, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os._exit(37)


class WorkingViewPrototypeTests(unittest.TestCase):
    @staticmethod
    def source(
        continuity: SQLiteHarnessRunContinuityStore,
        *,
        ref: str,
        generation: str,
        content: str,
    ):
        source = HarnessWorkingViewSource(
            logical_ref=ref,
            logical_generation=generation,
            messages=({"role": "user", "content": content},),
        )
        stored = continuity.store_working_view_source(source)
        return source, stored

    def test_metadata_only_contract_rejects_working_set_content_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = contract("pc11-working-metadata-only")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                spec = HarnessWorkingSetSpec.initial("working-attempt:metadata-only")
                with self.assertRaisesRegex(ValueError, "permission to persist model content"):
                    continuity.record_working_set(spec)

    def test_model_only_contract_rejects_tool_content_in_working_set_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = _private_content_contract("pc12a-working-tool-content")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                source = HarnessWorkingViewSource(
                    logical_ref="source://tool/current",
                    logical_generation="tool:g1",
                    messages=(
                        {
                            "role": "tool",
                            "toolCallId": "tool-call:pc12a-working",
                            "name": "search_workspace",
                            "content": "PRIVATE-TOOL-WORKING-SET-PC12A",
                        },
                    ),
                )
                with self.assertRaisesRegex(ValueError, "Tool content"):
                    continuity.store_working_view_source(source)
                # Deliberately bypass the policy-aware cognition API to prove that
                # Continuity still rejects a mechanically present unauthorized source.
                stored = store.put_object(
                    source.to_dict(), kind="harness-working-view-source"
                )
                spec = HarnessWorkingSetSpec.initial(
                    "working-attempt:pc12a-tool-content",
                    pins=(
                        HarnessWorkingSetPin(
                            slot="tool-evidence",
                            logical_ref=source.logical_ref,
                            logical_generation=source.logical_generation,
                            resolved_digest=stored.digest,
                        ),
                    ),
                )
                with self.assertRaisesRegex(ValueError, "Tool content"):
                    continuity.record_working_set(spec)

    def test_replace_commit_replan_preserves_history_and_exact_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = _private_content_contract("pc11-working-set")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                source_a, stored_a = self.source(
                    continuity,
                    ref="source://rule/current",
                    generation="git:a",
                    content="RULE=A",
                )
                source_b, stored_b = self.source(
                    continuity,
                    ref="source://rule/current",
                    generation="git:b",
                    content="RULE=B",
                )
                first = HarnessWorkingSetSpec.initial(
                    "working-attempt:1",
                    pins=(
                        HarnessWorkingSetPin(
                            slot="rule",
                            logical_ref=source_a.logical_ref,
                            logical_generation=source_a.logical_generation,
                            resolved_digest=stored_a.digest,
                        ),
                    ),
                )
                self.assertEqual(
                    continuity.record_working_set(first), HarnessEventAdmission.CREATED
                )
                self.assertEqual(
                    continuity.record_working_set(first), HarnessEventAdmission.EXISTING
                )
                first_view = compile_working_view(first, store)
                second = first.replace_pin(
                    HarnessWorkingSetPin(
                        slot="rule",
                        logical_ref=source_b.logical_ref,
                        logical_generation=source_b.logical_generation,
                        resolved_digest=stored_b.digest,
                    )
                )
                continuity.record_working_set(second)
                second_view = compile_working_view(second, store)
                self.assertNotEqual(first_view.digest, second_view.digest)
                self.assertEqual(first_view.messages[0]["content"], "RULE=A")
                self.assertEqual(second_view.messages[0]["content"], "RULE=B")
                committed = second.commit("current source B is sufficient")
                continuity.record_working_set(committed)
                with self.assertRaisesRegex(ValueError, "frozen"):
                    continuity.record_working_set(
                        committed.remove_pin("rule")
                    )
                replanned = committed.replan("working-attempt:2")
                self.assertEqual(replanned.previous_digest, committed.digest)
                self.assertEqual(replanned.parent_attempt_id, committed.attempt_id)
                continuity.record_working_set(replanned)
                self.assertEqual(continuity.load_current_working_set(), replanned)
                events = [
                    event
                    for event in store.list_run_events(run_contract.harness_run_id)
                    if event.event_kind == "harness.working-set-recorded"
                ]
                self.assertEqual(len(events), 4)
                self.assertEqual(continuity.doctor()["workingSets"], 4)
                # Old exact source remains independently readable after replacement/replan.
                self.assertEqual(
                    store.get_object(stored_a.digest, expected_kind="harness-working-view-source"),
                    source_a.to_dict(),
                )

    def test_continuity_doctor_rejects_semantically_broken_working_set_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = _private_content_contract("pc11-working-doctor")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                initial = HarnessWorkingSetSpec.initial("working-attempt:doctor")
                continuity.record_working_set(initial)
                # Bypass continuity admission to simulate a structurally intact but
                # semantically corrupted historical event. CAS/Event integrity alone
                # cannot prove the Working Set revision law.
                invalid = HarnessWorkingSetSpec(
                    attempt_id=initial.attempt_id,
                    revision=3,
                    previous_digest=initial.digest,
                    pins=(),
                )
                stored = store.put_object(
                    invalid.to_dict(), kind="harness-working-set-spec"
                )
                now = clock()
                lease = store.acquire_run_lease(
                    run_contract.harness_run_id,
                    owner_id="test:pc11-broken-working-set",
                    ttl_ms=5_000,
                    now_ms=now,
                )
                try:
                    store.append_event(
                        event_id="event:pc11-broken-working-set",
                        harness_run_id=run_contract.harness_run_id,
                        event_kind="harness.working-set-recorded",
                        data={
                            "workingSetDigest": invalid.digest,
                            "workingSetObjectDigest": stored.digest,
                            "attemptId": invalid.attempt_id,
                            "workingSetRevision": invalid.revision,
                            "committed": False,
                        },
                        expected_revision=lease.run_revision,
                        recorded_at_ms=now,
                        lease=lease,
                        lease_checked_at_ms=now,
                        referenced_objects=(stored,),
                    )
                finally:
                    store.release_run_lease(lease)
                self.assertTrue(store.doctor(full=True)["healthy"])
                with self.assertRaisesRegex(ValueError, "does not extend"):
                    continuity.doctor()

    def test_concurrent_working_set_writers_cannot_both_advance_one_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run_contract = _private_content_contract("pc11-working-race")
            clock = FixedClock()
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                source_a, stored_a = self.source(
                    continuity, ref="source://race/a", generation="g1", content="A"
                )
                source_b, stored_b = self.source(
                    continuity, ref="source://race/b", generation="g1", content="B"
                )
                initial = HarnessWorkingSetSpec.initial("working-attempt:race")
                continuity.record_working_set(initial)
                candidate_a = initial.replace_pin(
                    HarnessWorkingSetPin(
                        slot="evidence",
                        logical_ref=source_a.logical_ref,
                        logical_generation=source_a.logical_generation,
                        resolved_digest=stored_a.digest,
                    )
                )
                candidate_b = initial.replace_pin(
                    HarnessWorkingSetPin(
                        slot="evidence",
                        logical_ref=source_b.logical_ref,
                        logical_generation=source_b.logical_generation,
                        resolved_digest=stored_b.digest,
                    )
                )

            barrier = threading.Barrier(2)

            def write(spec: HarnessWorkingSetSpec) -> str:
                try:
                    with SQLiteHarnessStore(root) as store:
                        local = SQLiteHarnessRunContinuityStore.open(
                            store, run_contract.harness_run_id, clock_ms=FixedClock()
                        )
                        barrier.wait()
                        local.record_working_set(spec)
                    return "created"
                except Exception as error:
                    return type(error).__name__

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(write, (candidate_a, candidate_b)))
            self.assertEqual(outcomes.count("created"), 1, outcomes)
            with SQLiteHarnessStore(root) as store:
                continuity = SQLiteHarnessRunContinuityStore.open(
                    store, run_contract.harness_run_id, clock_ms=FixedClock()
                )
                head = continuity.load_current_working_set()
                self.assertIn(head, (candidate_a, candidate_b))
                events = [
                    event
                    for event in store.list_run_events(run_contract.harness_run_id)
                    if event.event_kind == "harness.working-set-recorded"
                ]
                self.assertEqual(len(events), 2)
                self.assertTrue(continuity.doctor()["healthy"])

    def test_metadata_only_provider_call_does_not_persist_exact_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = contract("pc11-provider-metadata-only")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                adapter = ScriptedTurnAdapter((completed_result("pc11-provider-metadata-only"),))
                bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
                loop = OrdivonAgentLoop(
                    adapter, bridge, budget=budget(), clock_ms=clock, monotonic_ms=clock
                )
                result = loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=({"role": "user", "content": "private text"},),
                )
                self.assertTrue(result.candidate_completed)
                retained = continuity.load_current_provider_call()
                self.assertEqual(retained.record.to_dict()["schemaVersion"], 4)
                self.assertIsNone(retained.request)
                self.assertIsNone(retained.request_object)
                self.assertEqual(
                    retained.record.result_digest,
                    completed_result("pc11-provider-metadata-only").digest,
                )
                self.assertIsNone(retained.result)
                self.assertIsNone(retained.result_object)
                provider_events = [
                    event
                    for event in store.list_run_events(run_contract.harness_run_id)
                    if event.event_kind.startswith("harness.provider-call-")
                ]
                self.assertTrue(
                    all(event.data.get("requestObjectDigest") is None for event in provider_events)
                )

    def test_product_provider_call_v3_retains_exact_agent_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = _private_content_contract("pc11-provider-v3")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                adapter = ScriptedTurnAdapter((completed_result("pc11-provider-v3"),))
                bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
                loop = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    assignment_deadline_ms=run_contract.deadline_ms,
                )
                result = loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "exact request evidence"},
                    ),
                )
                self.assertTrue(result.candidate_completed)
                retained = continuity.load_current_provider_call()
                self.assertEqual(retained.record.to_dict()["schemaVersion"], 3)
                self.assertIsNotNone(retained.request)
                self.assertIsNotNone(retained.request_object)
                assert retained.request is not None
                assert retained.request_object is not None
                self.assertEqual(retained.request, adapter.requests[0])
                self.assertEqual(
                    retained.request.dispatch_digest, retained.record.request_digest
                )
                self.assertEqual(
                    retained.request_object.digest,
                    retained.record.to_dict()["requestObjectDigest"],
                )
                provider_events = [
                    event
                    for event in store.list_run_events(run_contract.harness_run_id)
                    if event.event_kind.startswith("harness.provider-call-")
                ]
                self.assertEqual(len(provider_events), 3)
                self.assertTrue(
                    all(
                        event.data.get("requestObjectDigest")
                        == retained.request_object.digest
                        for event in provider_events
                    )
                )

            # Fresh process/store object reconstruction does not need caller transcript.
            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store, run_contract.harness_run_id, clock_ms=clock
                )
                recovered = reopened.load_current_provider_call()
                self.assertIsNotNone(recovered.request)
                assert recovered.request is not None
                self.assertEqual(
                    recovered.request.dispatch_digest, retained.record.request_digest
                )


    def test_projected_no_tool_turn_separates_run_state_from_model_view(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = _private_content_contract("pc11-projected")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                source, stored = self.source(
                    continuity,
                    ref="source://pc11/current",
                    generation="git:pc11",
                    content="TOKEN=ALPHA",
                )
                initial = HarnessWorkingSetSpec.initial(
                    "working-attempt:projected-1",
                    pins=(
                        HarnessWorkingSetPin(
                            slot="primary",
                            logical_ref=source.logical_ref,
                            logical_generation=source.logical_generation,
                            resolved_digest=stored.digest,
                        ),
                    ),
                )
                continuity.record_working_set(initial)
                committed = initial.commit("one exact source is sufficient")
                adapter = ScriptedTurnAdapter((completed_result("pc11-projected"),))
                execution = WorkingViewNoToolTurnRunner(
                    store,
                    run_contract,
                    continuity,
                    adapter,
                    budget=budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                ).run(committed)
                retained = continuity.load_current_provider_call()
                self.assertFalse(execution.replayed_provider_result)
                self.assertEqual(len(adapter.requests), 1)
                self.assertEqual(retained.state.messages, ())
                self.assertNotEqual(execution.working_view.messages, ())
                self.assertEqual(execution.request.messages, execution.working_view.messages)
                self.assertIsNotNone(retained.request)
                assert retained.request is not None
                self.assertEqual(retained.request.messages, execution.working_view.messages)
                self.assertEqual(
                    retained.request.dispatch_digest, execution.request.dispatch_digest
                )
                self.assertEqual(continuity.doctor()["workingSets"], 2)

    def test_projected_replan_uses_new_monotonic_provider_turn_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = _private_content_contract("pc11-projected-replan")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                source_a, stored_a = self.source(
                    continuity, ref="source://replan/current", generation="g:a", content="A"
                )
                source_b, stored_b = self.source(
                    continuity, ref="source://replan/current", generation="g:b", content="B"
                )
                initial = HarnessWorkingSetSpec.initial(
                    "working-attempt:replan-1",
                    pins=(
                        HarnessWorkingSetPin(
                            slot="primary",
                            logical_ref=source_a.logical_ref,
                            logical_generation=source_a.logical_generation,
                            resolved_digest=stored_a.digest,
                        ),
                    ),
                )
                continuity.record_working_set(initial)
                committed_a = initial.commit("attempt one evidence")
                first_adapter = ScriptedTurnAdapter((completed_result("pc11-replan-a"),))
                first = WorkingViewNoToolTurnRunner(
                    store, run_contract, continuity, first_adapter,
                    budget=budget(), clock_ms=clock, monotonic_ms=clock,
                ).run(committed_a)
                first_record = continuity.load_current_provider_call().record
                self.assertEqual(first.request.sequence, 1)

                replanned = committed_a.replan("working-attempt:replan-2")
                continuity.record_working_set(replanned)
                selected_b = replanned.replace_pin(
                    HarnessWorkingSetPin(
                        slot="primary",
                        logical_ref=source_b.logical_ref,
                        logical_generation=source_b.logical_generation,
                        resolved_digest=stored_b.digest,
                    )
                )
                continuity.record_working_set(selected_b)
                committed_b = selected_b.commit("attempt two refreshed evidence")
                second_adapter = ScriptedTurnAdapter((completed_result("pc11-replan-b"),))
                second = WorkingViewNoToolTurnRunner(
                    store, run_contract, continuity, second_adapter,
                    budget=budget(), clock_ms=clock, monotonic_ms=clock,
                ).run(committed_b)
                second_record = continuity.load_current_provider_call().record
                self.assertEqual(second.request.sequence, 2)
                self.assertNotEqual(
                    first_record.provider_call_id, second_record.provider_call_id
                )
                self.assertNotEqual(first.request.dispatch_digest, second.request.dispatch_digest)
                self.assertEqual(first.working_view.messages[0]["content"], "A")
                self.assertEqual(second.working_view.messages[0]["content"], "B")
                self.assertEqual(len(first_adapter.requests), 1)
                self.assertEqual(len(second_adapter.requests), 1)

    def test_projected_provider_result_replays_after_hard_process_exit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "state"
            code = (
                "from tests.test_pc1_working_view import "
                "_crash_after_projected_provider_completion as f; "
                f"f({str(root)!r})"
            )
            child = subprocess.run(
                [sys.executable, "-c", code],
                cwd=Path.cwd(),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(child.returncode, 37, (child.stdout, child.stderr))
            handoff = json.loads((base / "pc11-handoff.json").read_text())
            self.assertEqual(handoff["physicalProviderCalls"], 1)
            self.assertEqual(handoff["runStateMessages"], 0)
            self.assertGreater(handoff["requestMessages"], 0)

            clock = FixedClock()
            run_contract = _private_content_contract("pc11-projected-crash")
            with SQLiteHarnessStore(root) as store:
                continuity = SQLiteHarnessRunContinuityStore.open(
                    store, run_contract.harness_run_id, clock_ms=clock
                )
                committed = continuity.load_current_working_set()
                replay_adapter = ScriptedTurnAdapter(
                    (completed_result("should-not-physically-run"),)
                )
                execution = WorkingViewNoToolTurnRunner(
                    store,
                    run_contract,
                    continuity,
                    replay_adapter,
                    budget=budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                ).run(committed)
                self.assertTrue(execution.replayed_provider_result)
                self.assertEqual(replay_adapter.requests, [])
                self.assertEqual(
                    execution.working_view.digest, handoff["workingViewDigest"]
                )
                self.assertEqual(
                    execution.request.dispatch_digest,
                    handoff["requestDispatchDigest"],
                )
                retained = continuity.load_current_provider_call()
                self.assertEqual(retained.state.messages, ())
                self.assertIsNotNone(retained.request_object)
                assert retained.request_object is not None
                self.assertEqual(
                    retained.request_object.digest, handoff["requestObjectDigest"]
                )
                self.assertTrue(continuity.doctor()["healthy"])


if __name__ == "__main__":
    unittest.main()
