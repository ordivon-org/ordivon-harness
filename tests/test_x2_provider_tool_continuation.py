from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentTurnRequest,
    ProviderToolContinuation,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.run_store_port import HarnessProviderCallRequestMismatch
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.working_view import (
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingViewSource,
    WorkingSetViewProjector,
)

from tests.test_p0_sqlite_runtime_bridge import (
    FakeRuntime,
    FixedClock,
    bound_state as runtime_bound_state,
    budget as runtime_budget,
    completed_turn as runtime_completed_turn,
    contract as runtime_contract,
    execution_binding,
    tool_turn as runtime_tool_turn,
)
from tests.test_pc15_epistemic_control import (
    needs_input_turn,
    private_contract,
    run_budget,
    tool_call,
    tool_turn,
)
from tests.test_pc16_cross_process_tool_exchange import (
    CrashAfterFirstDurableObservationBridge,
    ProcessLost,
)


class ProviderToolContinuationTests(unittest.TestCase):
    def continuation(
        self, suffix: str, *, source_model_call_id: str
    ) -> ProviderToolContinuation:
        return ProviderToolContinuation(
            adapter_id=ScriptedTurnAdapter.adapter_id,
            source_turn_id=f"turn:{suffix}:1",
            source_model_call_id=source_model_call_id,
            opaque_state={
                "provider": "gemini-native",
                "modelContent": {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": "search_workspace",
                                "args": {"query": "continuation"},
                            },
                            "thoughtSignature": "OPAQUE_PROVIDER_SIGNATURE",
                        }
                    ],
                },
            },
        )

    def test_optional_continuation_roundtrips_without_changing_legacy_bytes(self) -> None:
        call = tool_call("tool-call:x2-roundtrip", "continuation")
        plain = tool_turn("x2-roundtrip", (call,))
        self.assertNotIn("providerToolContinuation", plain.to_dict())

        continuation = self.continuation(
            "x2-roundtrip", source_model_call_id=plain.model_call_id
        )
        result = replace(plain, provider_tool_continuation=continuation)
        self.assertEqual(result.provider_tool_continuation, continuation)
        self.assertEqual(type(result).from_dict(result.to_dict()), result)
        self.assertEqual(
            result.to_dict()["providerToolContinuation"], continuation.to_dict()
        )

        request = AgentTurnRequest(
            harness_run_id="harness-run:x2-roundtrip",
            turn_id="turn:x2-roundtrip:2",
            sequence=2,
            assignment_id="assignment:x2-roundtrip",
            context_digest="sha256:" + "a" * 64,
            tool_catalog_digest="sha256:" + "b" * 64,
            messages=({"role": "user", "content": "continue"},),
            tools=(),
            remaining_budget={"modelCalls": 1, "toolCalls": 0, "observationBytes": 1, "wallTimeMs": 1},
            provider_tool_continuations=(continuation,),
        )
        self.assertEqual(AgentTurnRequest.from_dict(request.to_dict()), request)
        self.assertEqual(
            request.to_dict()["providerToolContinuations"], [continuation.to_dict()]
        )
        legacy_request = replace(request, provider_tool_continuations=())
        self.assertNotIn("providerToolContinuations", legacy_request.to_dict())

    def test_continuation_requires_tool_result_and_exact_source_model_call(self) -> None:
        base_invalid = tool_turn(
            "x2-invalid", (tool_call("tool-call:x2-invalid-base", "continuation"),)
        )
        continuation = self.continuation(
            "x2-invalid", source_model_call_id=base_invalid.model_call_id
        )
        with self.assertRaisesRegex(ValueError, "Tool-bearing"):
            replace(
                needs_input_turn("x2-invalid", "unknown"),
                provider_tool_continuation=continuation,
            )
        call = tool_call("tool-call:x2-invalid", "continuation")
        with self.assertRaisesRegex(ValueError, "Model Call"):
            replace(
                tool_turn("x2-invalid", (call,)),
                provider_tool_continuation=replace(
                    continuation,
                    source_model_call_id="model-call:other",
                ),
            )

    def test_external_initial_messages_cannot_inject_reserved_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = runtime_contract("x2-ingress-injection")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store, run_contract, clock_ms=clock
            )
            runtime = FakeRuntime("direct")
            bridge = SQLiteHarnessRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                runtime,
            )
            adapter = ScriptedTurnAdapter(
                (needs_input_turn("x2-ingress-injection", "must not invoke"),)
            )
            loop = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=runtime_budget(),
                clock_ms=clock,
                monotonic_ms=clock,
            )
            with self.assertRaisesRegex(
                ValueError, "cannot supply Harness-reserved Provider Tool continuation"
            ):
                loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {
                            "role": "assistant",
                            "content": None,
                            "toolCalls": [
                                tool_call(
                                    "tool-call:x2-ingress-injection", "continuation"
                                ).to_dict()
                            ],
                            "providerToolContinuation": self.continuation(
                                "x2-ingress-injection",
                                source_model_call_id="model-call:forged",
                            ).to_dict(),
                        },
                    ),
                )
            self.assertEqual(len(adapter.requests), 0)
            self.assertEqual(runtime.workspace_exec_count, 0)
            self.assertTrue(store.doctor(full=True)["healthy"])
            store.close()

    def test_no_working_view_projects_continuation_outside_model_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = runtime_contract("x2-no-working-view")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store, run_contract, clock_ms=clock
            )
            runtime = FakeRuntime("direct")
            bridge = SQLiteHarnessRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                runtime,
            )
            first = runtime_tool_turn("x2-no-working-view")
            continuation = ProviderToolContinuation(
                adapter_id=ScriptedTurnAdapter.adapter_id,
                source_turn_id="turn:p0-runtime-x2-no-working-view:1",
                source_model_call_id=first.model_call_id,
                opaque_state={"thoughtSignature": "OPAQUE_NO_VIEW_SIGNATURE"},
            )
            first = replace(first, provider_tool_continuation=continuation)
            adapter = ScriptedTurnAdapter(
                (first, runtime_completed_turn("x2-no-working-view"))
            )
            loop = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=runtime_budget(),
                clock_ms=clock,
                monotonic_ms=clock,
            )
            result = loop.run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "search once"},),
            )
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertEqual(len(adapter.requests), 2)
            second = adapter.requests[1]
            self.assertEqual(second.provider_tool_continuations, (continuation,))
            self.assertNotIn("OPAQUE_NO_VIEW_SIGNATURE", str(second.messages))
            self.assertTrue(store.doctor(full=True)["healthy"])
            store.close()

    def test_wrong_continuation_authority_stops_before_tool_dispatch(self) -> None:
        for label, mutate in (
            ("adapter", {"adapter_id": "adapter:foreign"}),
            ("turn", {"source_turn_id": "turn:foreign:1"}),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "state"
                clock = FixedClock()
                run_contract = runtime_contract(f"x2-wrong-{label}")
                store = SQLiteHarnessStore.initialize(root)
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                runtime = FakeRuntime("direct")
                bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    continuity,
                    execution_binding(run_contract, continuity),
                    runtime,
                )
                first = runtime_tool_turn(f"x2-wrong-{label}")
                continuation = ProviderToolContinuation(
                    adapter_id=ScriptedTurnAdapter.adapter_id,
                    source_turn_id=(
                        f"turn:p0-runtime-x2-wrong-{label}:1"
                    ),
                    source_model_call_id=first.model_call_id,
                    opaque_state={"opaque": label},
                )
                first = replace(
                    first,
                    provider_tool_continuation=replace(continuation, **mutate),
                )
                adapter = ScriptedTurnAdapter((first,))
                loop = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=runtime_budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                )
                result = loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=({"role": "user", "content": "search once"},),
                )
                self.assertEqual(result.stop_code, RunStopCode.INVALID_MODEL_OUTPUT)
                self.assertEqual(runtime.workspace_exec_count, 0)
                self.assertTrue(store.doctor(full=True)["healthy"])
                store.close()

    def test_metadata_only_provider_completion_does_not_retain_opaque_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = runtime_contract("x2-metadata-only")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store, run_contract, clock_ms=clock
            )
            continuity.bind_state(runtime_bound_state())
            claimed = continuity.claim_provider_call(
                source=continuity.assignment_provider_source(),
                turn_id="turn:p0-runtime-x2-metadata-only:1",
                turn_sequence=1,
                request_digest="sha256:" + "1" * 64,
                provider_request_digest="sha256:" + "2" * 64,
                adapter_id=ScriptedTurnAdapter.adapter_id,
                requested_model_id=ScriptedTurnAdapter.model_id,
                holder_id="holder:x2-metadata-only",
                ttl_ms=10_000,
            )
            dispatching = continuity.mark_provider_call_dispatching(claimed)
            first = runtime_tool_turn("x2-metadata-only")
            continuation = ProviderToolContinuation(
                adapter_id=ScriptedTurnAdapter.adapter_id,
                source_turn_id="turn:p0-runtime-x2-metadata-only:1",
                source_model_call_id=first.model_call_id,
                opaque_state={"secretLikeOpaqueState": "MUST_NOT_BE_RETAINED"},
            )
            completed = continuity.complete_provider_call(
                dispatching,
                replace(first, provider_tool_continuation=continuation),
            )
            self.assertIsNone(completed.result)
            self.assertIsNone(completed.result_object)
            self.assertIsNone(completed.record.result_object_digest)
            self.assertTrue(store.doctor(full=True)["healthy"])
            store.close()

    def test_fresh_process_restores_opaque_continuation_outside_model_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract(
                "x2-provider-continuation",
                max_model_calls=2,
                max_tool_calls=1,
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store, run_contract, clock_ms=clock
            )
            source = HarnessWorkingViewSource(
                logical_ref="source://x2/provider-continuation",
                logical_generation="generation:1",
                messages=(
                    {"role": "user", "content": "Use the exact Tool then continue."},
                ),
            )
            stored = continuity.store_working_view_source(source)
            pin = HarnessWorkingSetPin(
                slot="primary",
                logical_ref=source.logical_ref,
                logical_generation=source.logical_generation,
                resolved_digest=stored.digest,
            )
            initial = HarnessWorkingSetSpec.initial(
                "working-attempt:x2-continuation",
                pins=(pin,),
            )
            continuity.record_working_set(initial)
            continuity.record_working_set(initial.commit("seed x2 continuation view"))

            call = tool_call("tool-call:x2-continuation", "continuation")
            first_result = tool_turn("x2-provider-continuation", (call,))
            continuation = ProviderToolContinuation(
                adapter_id=ScriptedTurnAdapter.adapter_id,
                source_turn_id="turn:p0-runtime-x2-provider-continuation:1",
                source_model_call_id=first_result.model_call_id,
                opaque_state={"thoughtSignature": "OPAQUE_PROVIDER_SIGNATURE"},
            )
            first_result = replace(
                first_result,
                provider_tool_continuation=continuation,
            )
            first_runtime = FakeRuntime("direct")
            first_bridge = CrashAfterFirstDurableObservationBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                first_runtime,
            )
            first_loop = OrdivonAgentLoop(
                ScriptedTurnAdapter((first_result,)),
                first_bridge,
                budget=run_budget(max_model_calls=2, max_tool_calls=1),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
            )
            with self.assertRaises(ProcessLost):
                first_loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "canonical x2 root"},
                    ),
                )
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained = reopened.load_current_snapshot()
                class TamperingProviderRequestBridge(SQLiteHarnessRuntimeBridge):
                    def begin_provider_call(
                        self, request, *, provider_request_digest=None
                    ):
                        if request.provider_tool_continuations:
                            current = request.provider_tool_continuations[0]
                            request = replace(
                                request,
                                provider_tool_continuations=(
                                    replace(
                                        current,
                                        opaque_state={
                                            "thoughtSignature": "TAMPERED_BEFORE_VERIFIER"
                                        },
                                    ),
                                ),
                            )
                        return super().begin_provider_call(
                            request,
                            provider_request_digest=provider_request_digest,
                        )

                tamper_runtime = FakeRuntime("direct")
                tamper_bridge = TamperingProviderRequestBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    tamper_runtime,
                    provider_source=reopened.snapshot_provider_source(retained),
                )
                tamper_adapter = ScriptedTurnAdapter(
                    (needs_input_turn("x2-tampered", "must not invoke"),)
                )
                tamper_loop = OrdivonAgentLoop(
                    tamper_adapter,
                    tamper_bridge,
                    budget=run_budget(max_model_calls=2, max_tool_calls=1),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(
                        reopened_store, reopened
                    ),
                )
                with self.assertRaisesRegex(
                    HarnessProviderCallRequestMismatch,
                    "Provider Tool continuation",
                ):
                    tamper_loop.resume(
                        retained=retained,
                        assignment_id=reopened.binding.assignment_id,
                        context_digest=run_contract.context_refs[0].digest,
                    )
                self.assertEqual(len(tamper_adapter.requests), 0)
                self.assertEqual(tamper_runtime.workspace_exec_count, 0)

                retained = reopened.load_current_snapshot()
                runtime = FakeRuntime("direct")
                bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    runtime,
                    provider_source=reopened.snapshot_provider_source(retained),
                )
                adapter = ScriptedTurnAdapter(
                    (needs_input_turn("x2-resumed", "bounded unknown"),)
                )
                loop = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=run_budget(max_model_calls=2, max_tool_calls=1),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(
                        reopened_store, reopened
                    ),
                )
                result = loop.resume(
                    retained=retained,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                )
                self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertEqual(len(adapter.requests), 1)
                request = adapter.requests[0]
                self.assertEqual(request.provider_tool_continuations, (continuation,))
                self.assertNotIn(
                    "OPAQUE_PROVIDER_SIGNATURE",
                    str(request.messages),
                )
                self.assertEqual(runtime.workspace_exec_count, 0)
                self.assertTrue(reopened.doctor()["healthy"])


if __name__ == "__main__":
    unittest.main()
