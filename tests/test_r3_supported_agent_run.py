from __future__ import annotations

import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from anc_canonical import canonical_digest

from ordivon_harness.api import (
    AgentTurnResult,
    HarnessAgentRun,
    HarnessAgentRunCompositionError,
    HarnessBoundReference,
    HarnessCognitionProfile,
    HarnessCognitionSeed,
    HarnessCognitionSeedSource,
    HarnessExecutionBinding,
    HarnessPrivacyPolicy,
    HarnessRunContract,
    HarnessRuntimeReference,
    HarnessCognitionSource,
)
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.sqlite_agent_bridge import (
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
)
from ordivon_harness.ordivon.sqlite_runtime_bridge import (
    INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST,
    INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST,
)


class FixedClock:
    def __init__(self):
        self.value = 1000

    def __call__(self):
        return self.value


def digest(label: str) -> str:
    return canonical_digest({"r3": label})


def contract(
    suffix: str,
    *,
    tools: bool = False,
    model_id: str = ScriptedTurnAdapter.model_id,
    allow_model_content: bool = True,
    allow_tool_content: bool | None = None,
    completion_contract=None,
):
    return HarnessRunContract(
        harness_run_id=f"harness-run:r3-{suffix}",
        harness_implementation_id="ordivon-harness@r3",
        caller_id="caller:r3",
        caller_run_ref=f"trial:r3-{suffix}",
        objective_ref=HarnessBoundReference("objective:r3", "objective", digest("objective")),
        context_refs=(HarnessBoundReference("context:r3", "context", digest("context")),),
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=model_id,
        tool_catalog_digest=(
            INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST if tools else NO_TOOL_AGENT_SURFACE_DIGEST
        ),
        tool_grant_digest=(
            INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST if tools else NO_TOOL_AGENT_GRANT_DIGEST
        ),
        budget={
            "maxModelCalls": 4,
            "maxToolCalls": 2 if tools else 0,
            "maxObservationBytes": 65536,
            "maxWallTimeMs": 10000,
            "maxTotalTokens": 10000,
            "maxModelRetries": 1,
            "maxToolCorrections": 2,
            "maxConclusionCorrections": 3,
            "maxObservationOnlyTurns": 4,
            "maxNoProgressTurns": 3,
        },
        completion_contract=completion_contract or {"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            "manifest:r3", "system-manifest", digest("manifest")
        ),
        created_at_ms=1000,
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=allow_model_content,
            allow_tool_content=(tools if allow_tool_content is None else allow_tool_content),
        ),
    )


def needs_input(call_id: str = "model-call:r3-needs") -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=call_id,
        model_id=ScriptedTurnAdapter.model_id,
        content="need caller input",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="needs_input",
            summary="Need caller input.",
            unresolved_unknowns=("caller reply",),
        ),
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="stop",
        raw_response_digest=digest(call_id),
    )


def completed(call_id: str = "model-call:r3-done") -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=call_id,
        model_id=ScriptedTurnAdapter.model_id,
        content="done",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="R3 completed.",
        ),
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="stop",
        raw_response_digest=digest(call_id),
    )


class FakeRuntime:
    def call_tool(self, name, arguments):
        if name != "workspace.exec":
            raise AssertionError(name)
        return {
            "status": "succeeded",
            "jobId": "job:r3-runtime",
            "attemptId": "attempt:r3-runtime",
            "executionTerminal": True,
            "executionDisposition": "succeeded",
            "deliveryDisposition": "committed",
            "recoveryRequired": False,
            "semanticCompletionEvaluated": False,
            "exitCode": 0,
            "stdoutTail": "needle",
            "stderrTail": "",
            "resultAvailable": True,
            "artifactsAvailable": False,
        }

    def find_jobs_by_client_request_id(self, client_request_id):
        return ()


def execution_binding(value: HarnessRunContract) -> HarnessExecutionBinding:
    token = value.digest[7:31]
    return HarnessExecutionBinding(
        harness_run_id=value.harness_run_id,
        workspace_ref="workspace:r3-explicit",
        assignment_id=f"assignment:external:{token}",
        assignment_generation=1,
        assignment_digest=value.digest,
        runtime_binding_digest=digest("runtime-binding"),
        tool_catalog_digest=value.tool_catalog_digest,
        tool_grant_digest=value.tool_grant_digest,
        deadline_ms=value.deadline_ms,
        runtime_references=(
            HarnessRuntimeReference(
                namespace="ordivon.harness",
                reference_type="harness_run",
                reference_id=value.harness_run_id,
                generation="1",
                digest=value.digest,
            ),
        ),
    )


class R3SupportedAgentRunTests(unittest.TestCase):
    def test_create_run_pause_open_resume_hides_continuity_and_provider_source(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = FixedClock()
            value = contract("resume")
            root = Path(directory) / "state"
            first = HarnessAgentRun.create(
                root,
                value,
                lambda _contract: ScriptedTurnAdapter((needs_input(),)),
                clock_ms=clock,
                monotonic_ms=clock,
            )
            paused = first.run(({"role": "user", "content": "start"},))
            self.assertTrue(paused.paused)
            reopened = HarnessAgentRun.open(
                root,
                value.harness_run_id,
                lambda _contract: ScriptedTurnAdapter((completed(),)),
                clock_ms=clock,
                monotonic_ms=clock,
            )
            done = reopened.resume(additional_messages=({"role": "user", "content": "answer"},))
            self.assertEqual(done.loop_result.stop_code.value, "candidate_completed")
            self.assertTrue(reopened.doctor()["healthy"])

    def test_cognition_seed_is_caller_owned_but_composition_is_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = FixedClock()
            value = contract("cognition")
            adapter = ScriptedTurnAdapter((needs_input("model-call:r3-cognition"),))
            root = Path(directory) / "state"
            run = HarnessAgentRun.create(
                root,
                value,
                lambda _contract: adapter,
                clock_ms=clock,
                monotonic_ms=clock,
                cognition_profile=HarnessCognitionProfile(
                    working_set_transitions=True,
                    caller_ingress_promotions=True,
                    working_set_history=False,
                ),
            )
            seed = HarnessCognitionSeed(
                attempt_id="working-attempt:r3-seed",
                sources=(
                    HarnessCognitionSeedSource(
                        slot="task",
                        source=HarnessCognitionSource(
                            logical_ref="source://r3/task",
                            logical_generation="g1",
                            messages=({"role": "user", "content": "durable task"},),
                        ),
                    ),
                ),
                basis="caller selected exact R3 source",
            )
            run.run((), cognition_seed=seed)
            self.assertEqual(adapter.requests[0].messages[0]["content"], "durable task")
            self.assertTrue(adapter.requests[0].capabilities.working_set_transition)

    def test_runtime_tool_surface_requires_explicit_external_execution_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = FixedClock()
            value = contract("runtime", tools=True)
            tool = AgentToolCall(
                tool_call_id="tool-call:r3-search",
                name="search_workspace",
                arguments={"query": "needle"},
            )
            tool_turn = AgentTurnResult(
                model_call_id="model-call:r3-tool",
                model_id=ScriptedTurnAdapter.model_id,
                content="search",
                tool_calls=(tool,),
                conclusion=None,
                usage={"inputTokens": 1, "outputTokens": 1},
                finish_reason="tool_calls",
                raw_response_digest=digest("tool-turn"),
            )
            adapter = ScriptedTurnAdapter((tool_turn, completed("model-call:r3-runtime-done")))
            root = Path(directory) / "state"
            with self.assertRaisesRegex(
                HarnessAgentRunCompositionError, "requires exact execution binding"
            ):
                HarnessAgentRun.create(
                    root,
                    value,
                    lambda _contract: adapter,
                    clock_ms=clock,
                    monotonic_ms=clock,
                )
            run = HarnessAgentRun.create(
                root,
                value,
                lambda _contract: adapter,
                clock_ms=clock,
                monotonic_ms=clock,
                execution_binding=execution_binding(value),
                runtime=FakeRuntime(),
            )
            result = run.run(({"role": "user", "content": "search"},))
            self.assertEqual(result.loop_result.stop_code.value, "candidate_completed")
            self.assertEqual(result.loop_result.usage["toolCalls"], 1)

    def test_concurrent_public_handles_dispatch_one_physical_provider_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            value = contract("concurrent")
            HarnessAgentRun.create(
                root,
                value,
                lambda _contract: ScriptedTurnAdapter((completed("model-call:r3-bootstrap"),)),
            )
            workers = 8
            barrier = threading.Barrier(workers)
            physical_calls: list[int] = []
            lock = threading.Lock()

            class CountingAdapter(ScriptedTurnAdapter):
                def __init__(self, worker: int):
                    super().__init__((completed(f"model-call:r3-worker-{worker}"),))
                    self.worker = worker

                def invoke(self, request):
                    with lock:
                        physical_calls.append(self.worker)
                    time.sleep(0.03)
                    return super().invoke(request)

            def execute(worker: int) -> str:
                clock = FixedClock()
                handle = HarnessAgentRun.open(
                    root,
                    value.harness_run_id,
                    lambda _contract: CountingAdapter(worker),
                    clock_ms=clock,
                    monotonic_ms=clock,
                )
                barrier.wait()
                try:
                    handle.run(({"role": "user", "content": "complete"},))
                    return "ok"
                except Exception as error:  # durable claim losers must not dispatch
                    return type(error).__name__

            with ThreadPoolExecutor(max_workers=workers) as pool:
                outcomes = list(pool.map(execute, range(workers)))

            self.assertEqual(len(physical_calls), 1)
            self.assertEqual(outcomes.count("ok"), 1)

    def test_invalid_surface_fails_before_provider_factory_is_called(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            value = contract("invalid-before-provider", tools=True)
            calls = 0

            def provider_factory(_contract):
                nonlocal calls
                calls += 1
                raise AssertionError("Provider factory must not run")

            with self.assertRaisesRegex(
                HarnessAgentRunCompositionError, "requires exact execution binding"
            ):
                HarnessAgentRun.create(root, value, provider_factory)
            self.assertEqual(calls, 0)
            self.assertFalse(root.exists())

    def test_adapter_mismatch_fails_before_durable_run_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            value = contract("adapter-mismatch")
            wrong = ScriptedTurnAdapter((completed("model-call:r3-wrong"),))
            wrong.model_id = "model:r3-wrong"
            with self.assertRaisesRegex(HarnessAgentRunCompositionError, "requested model differs"):
                HarnessAgentRun.create(root, value, lambda _contract: wrong)
            self.assertFalse(root.exists())

    def test_cognition_privacy_fails_before_provider_factory_or_state_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            value = contract("cognition-privacy", allow_model_content=False)
            calls = 0

            def provider_factory(_contract):
                nonlocal calls
                calls += 1
                raise AssertionError("Provider factory must not run")

            with self.assertRaisesRegex(
                HarnessAgentRunCompositionError,
                "cognition requires Contract permission",
            ):
                HarnessAgentRun.create(
                    root,
                    value,
                    provider_factory,
                    cognition_profile=HarnessCognitionProfile(),
                )
            self.assertEqual(calls, 0)
            self.assertFalse(root.exists())

    def test_cognition_history_privacy_fails_before_provider_factory_or_state_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            value = contract("cognition-history-privacy")
            calls = 0

            def provider_factory(_contract):
                nonlocal calls
                calls += 1
                raise AssertionError("Provider factory must not run")

            with self.assertRaisesRegex(
                HarnessAgentRunCompositionError,
                "history requires Tool-content authority",
            ):
                HarnessAgentRun.create(
                    root,
                    value,
                    provider_factory,
                    cognition_profile=HarnessCognitionProfile.full(),
                )
            self.assertEqual(calls, 0)
            self.assertFalse(root.exists())

    def test_runtime_binding_mismatch_fails_before_provider_factory_or_state_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            value = contract("binding-preflight", tools=True)
            binding = execution_binding(value)
            invalid = HarnessExecutionBinding(
                harness_run_id=binding.harness_run_id,
                workspace_ref=binding.workspace_ref,
                assignment_id=binding.assignment_id,
                assignment_generation=2,
                assignment_digest=binding.assignment_digest,
                runtime_binding_digest=binding.runtime_binding_digest,
                tool_catalog_digest=binding.tool_catalog_digest,
                tool_grant_digest=binding.tool_grant_digest,
                deadline_ms=binding.deadline_ms,
                runtime_references=binding.runtime_references,
            )
            calls = 0

            def provider_factory(_contract):
                nonlocal calls
                calls += 1
                raise AssertionError("Provider factory must not run")

            with self.assertRaisesRegex(
                HarnessAgentRunCompositionError, "differs from the independent Run binding"
            ):
                HarnessAgentRun.create(
                    root,
                    value,
                    provider_factory,
                    execution_binding=invalid,
                    runtime=FakeRuntime(),
                )
            self.assertEqual(calls, 0)
            self.assertFalse(root.exists())

    def test_structured_completion_mismatch_fails_before_state_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            value = contract(
                "structured-preflight",
                completion_contract={
                    "mode": "structured-result-v1",
                    "resultKind": "r3-preflight",
                    "resultSchema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"choice": {"type": "string"}},
                        "required": ["choice"],
                    },
                },
            )
            calls = 0

            def provider_factory(_contract):
                nonlocal calls
                calls += 1
                return ScriptedTurnAdapter((completed(),))

            with self.assertRaisesRegex(
                HarnessAgentRunCompositionError, "structured completion differs"
            ):
                HarnessAgentRun.create(root, value, provider_factory)
            self.assertEqual(calls, 1)
            self.assertFalse(root.exists())

    def test_unknown_tool_surface_fails_instead_of_guessing_a_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = FixedClock()
            raw = contract("unknown").to_dict()
            raw["toolCatalogDigest"] = digest("unknown-catalog")
            raw["toolGrantDigest"] = digest("unknown-grant")
            value = HarnessRunContract.from_dict(raw)
            root = Path(directory) / "state"
            with self.assertRaisesRegex(HarnessAgentRunCompositionError, "does not implement"):
                HarnessAgentRun.create(
                    root,
                    value,
                    lambda _contract: ScriptedTurnAdapter((completed(),)),
                    clock_ms=clock,
                    monotonic_ms=clock,
                )
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
