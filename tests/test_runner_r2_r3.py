from __future__ import annotations

import tempfile
import unittest
from typing import Any

from anc_canonical import canonical_digest
from ordivon_host import HostStorage
from ordivon_host.runtime import RuntimeProtocolError, RuntimeTransportError
from test_ordivon_harness_oh2 import _Runtime, _committed
from test_ordivon_harness_oh5 import (
    _RecoveryRuntime,
    _assign,
    _create_task,
    _grant,
)
from test_runner_r0_r1 import _clock, _completion, _plan

from ordivon_harness import HarnessHost, HarnessRunner, ToolGrant
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    AgentToolCall,
    AgentToolDefinition,
    AgentTurnAdapterError,
    AgentTurnFailureCode,
    AgentTurnResult,
    CancellationToken,
    ExecutionControl,
    HostHarnessRunStore,
    OrdivonAgentLoop,
    RunBudget,
    RunDeadline,
    RunStopCode,
    RuntimeToolBridge,
    ScriptedTurnAdapter,
    ToolBridgeError,
    ToolBridgeErrorKind,
    ToolObservation,
    discover_harness_runtime_catalog,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 10_000

    def __call__(self) -> int:
        self.value += 1
        return self.value


class _LoopBridge:
    catalog_digest = canonical_digest({"catalog": "r2-r3"})

    def __init__(self) -> None:
        self.attempts = 0
        self.effects = 0

    def definitions(self) -> tuple[AgentToolDefinition, ...]:
        return (
            AgentToolDefinition(
                "read_workspace",
                "Read a bounded fixture file.",
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"relativePath": {"type": "string"}},
                    "required": ["relativePath"],
                },
            ),
        )

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        del step_id
        self.attempts += 1
        if call.arguments.get("relativePath") == "bad":
            raise ToolBridgeError(
                "relativePath must identify an admitted file",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        self.effects += 1
        return ToolObservation(
            call.tool_call_id,
            call.name,
            "observed",
            {
                "content": "ok",
                "digest": canonical_digest("ok"),
            },
        )


class _RetryAdapter:
    adapter_id = "ordivon.test-retry-adapter.v1"
    model_id = "ordivon.test-retry-model.v1"
    supports_call_handle = False

    def __init__(self, outcomes: list[AgentTurnResult | BaseException]) -> None:
        self.outcomes = outcomes
        self.requests = []

    def invoke_with_control(self, request, control):
        del control
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def invoke(self, request):
        raise AssertionError(request)


def _turn(
    suffix: str,
    *,
    model_id: str,
    calls: tuple[AgentToolCall, ...] = (),
    conclusion: AgentRunConclusion | None = None,
    usage: dict[str, Any] | None = None,
) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:r2-r3:{suffix}",
        model_id=model_id,
        content=None,
        tool_calls=calls,
        conclusion=conclusion,
        usage=usage or {"total_tokens": 15},
        finish_reason="tool_calls" if calls else "stop",
        raw_response_digest=canonical_digest({"response": suffix}),
    )


class _PatchRuntime(_Runtime):
    def __init__(self, *, lose_first_response: bool = True) -> None:
        super().__init__()
        self.lose_first_response = lose_first_response
        self.physical_effects = 0
        self.patch_requests: dict[str, dict[str, Any]] = {}
        self.patch_receipts: dict[str, dict[str, Any]] = {}

    def list_tools(self) -> tuple[dict[str, Any], ...]:
        values = list(super().list_tools())
        for name in ("workspace.patch", "workspace.patch.get"):
            values.append(
                {
                    "name": name,
                    "inputSchema": {"type": "object", "properties": {}},
                    "outputSchema": {"type": "object"},
                    "execution": "synchronous",
                }
            )
        return tuple(values)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "workspace.patch":
            self.calls.append((name, dict(arguments)))
            request_id = str(arguments["clientRequestId"])
            existing = self.patch_requests.get(request_id)
            if existing is not None:
                if canonical_digest(existing) != canonical_digest(arguments):
                    raise AssertionError("idempotent patch replay changed arguments")
                return {
                    **self.patch_receipts[request_id],
                    "replayed": True,
                }
            self.physical_effects += 1
            self.patch_requests[request_id] = dict(arguments)
            receipt = {
                "operationId": f"patch-operation:{request_id}",
                "clientRequestId": request_id,
                "requestDigest": canonical_digest(arguments),
                "replayed": False,
                "patch": {
                    "files": [],
                    "diff": "fixture patch",
                    "diffTruncated": False,
                },
            }
            self.patch_receipts[request_id] = receipt
            if self.lose_first_response:
                self.lose_first_response = False
                raise RuntimeTransportError(
                    "patch response was lost after physical commitment"
                )
            return receipt
        if name == "workspace.patch.get":
            self.calls.append((name, dict(arguments)))
            request_id = str(arguments["clientRequestId"])
            receipt = self.patch_receipts[request_id]
            return {
                "operationId": receipt["operationId"],
                "clientRequestId": request_id,
                "requestDigest": receipt["requestDigest"],
                "workspaceId": self.patch_requests[request_id]["workspaceId"],
                "state": "committed",
                "patch": receipt["patch"],
            }
        return super().call_tool(name, arguments)


class _PartialPatchRuntime(_Runtime):
    def list_tools(self) -> tuple[dict[str, Any], ...]:
        return super().list_tools() + (
            {
                "name": "workspace.patch",
                "inputSchema": {"type": "object"},
                "outputSchema": {"type": "object"},
                "execution": "synchronous",
            },
        )


class _InjectedCrash(BaseException):
    pass


class _CrashPatchRuntime(_RecoveryRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.physical_effects = 0
        self.patch_requests: dict[str, dict[str, Any]] = {}
        self.crash_once = True

    def list_tools(self) -> tuple[dict[str, Any], ...]:
        values = list(super().list_tools())
        for name in ("workspace.patch", "workspace.patch.get"):
            values.append(
                {
                    "name": name,
                    "inputSchema": {"type": "object", "properties": {}},
                    "outputSchema": {"type": "object"},
                    "execution": "synchronous",
                }
            )
        return tuple(values)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "workspace.patch":
            self.calls.append((name, dict(arguments)))
            request_id = str(arguments["clientRequestId"])
            if request_id not in self.patch_requests:
                self.patch_requests[request_id] = dict(arguments)
                self.physical_effects += 1
            if self.crash_once:
                self.crash_once = False
                raise _InjectedCrash()
            raise AssertionError("restart reconciliation must not redispatch patch")
        if name == "workspace.patch.get":
            self.calls.append((name, dict(arguments)))
            request_id = str(arguments["clientRequestId"])
            request = self.patch_requests[request_id]
            return {
                "operationId": f"patch-operation:{request_id}",
                "clientRequestId": request_id,
                "requestDigest": canonical_digest(request),
                "workspaceId": request["workspaceId"],
                "state": "committed",
                "patch": {
                    "files": [],
                    "diff": "fixture patch",
                    "diffTruncated": False,
                },
            }
        return super().call_tool(name, arguments)


class HarnessR2R3Tests(unittest.TestCase):
    def test_transient_provider_retry_reuses_logical_turn_and_dispatches_once(
        self,
    ) -> None:
        call = AgentToolCall(
            "tool-call:r2-r3:retry-read",
            "read_workspace",
            {"relativePath": "README.md"},
        )
        adapter = _RetryAdapter(
            [
                AgentTurnAdapterError(
                    "temporary transport failure",
                    failure_code=AgentTurnFailureCode.TRANSPORT_FAILED,
                ),
                _turn("retry-success", model_id=_RetryAdapter.model_id, calls=(call,)),
                _turn(
                    "retry-complete",
                    model_id=_RetryAdapter.model_id,
                    conclusion=AgentRunConclusion(
                        "candidate_completed",
                        "The retried logical turn completed without duplicate effect.",
                    ),
                ),
            ]
        )
        bridge = _LoopBridge()
        live_events = []
        result = OrdivonAgentLoop(
            adapter,
            bridge,
            budget=RunBudget(4, 4, 64_000, 10_000, 1_000, 1, 1),
            clock_ms=_Clock(),
            event_sink=live_events.append,
        ).run(
            harness_run_id="harness-run:r2-r3-provider-retry",
            assignment_id="assignment:r2-r3-provider-retry",
            context_digest=canonical_digest({"context": "provider-retry"}),
            initial_messages=({"role": "user", "content": "inspect"},),
        )

        self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
        self.assertEqual(bridge.effects, 1)
        self.assertEqual(len(adapter.requests), 3)
        self.assertEqual(adapter.requests[0].digest, adapter.requests[1].digest)
        self.assertEqual(result.usage["modelRetries"], 1)
        self.assertEqual(result.usage["providerAttempts"], 3)
        self.assertEqual(tuple(live_events), result.trace.events)
        kinds = [event.kind for event in result.trace.events]
        self.assertEqual(kinds.count("model_call_retry_scheduled"), 1)
        self.assertEqual(kinds.count("tool_call_dispatched"), 1)

    def test_provider_timeout_is_not_retried(self) -> None:
        adapter = _RetryAdapter(
            [
                AgentTurnAdapterError(
                    "provider timeout",
                    failure_code=AgentTurnFailureCode.TIMEOUT,
                )
            ]
        )
        result = OrdivonAgentLoop(
            adapter,
            _LoopBridge(),
            budget=RunBudget(3, 3, 64_000, 10_000, 1_000, 3, 1),
            clock_ms=_Clock(),
        ).run(
            harness_run_id="harness-run:r2-r3-provider-timeout",
            assignment_id="assignment:r2-r3-provider-timeout",
            context_digest=canonical_digest({"context": "provider-timeout"}),
            initial_messages=({"role": "user", "content": "inspect"},),
        )

        self.assertEqual(result.stop_code, RunStopCode.PROVIDER_TIMEOUT)
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(result.usage["modelRetries"], 0)

    def test_local_tool_rejection_returns_to_model_without_effect(self) -> None:
        bad = AgentToolCall(
            "tool-call:r2-r3:bad",
            "read_workspace",
            {"relativePath": "bad"},
        )
        good = AgentToolCall(
            "tool-call:r2-r3:good",
            "read_workspace",
            {"relativePath": "README.md"},
        )
        adapter = ScriptedTurnAdapter(
            (
                _turn("bad-tool", model_id=ScriptedTurnAdapter.model_id, calls=(bad,)),
                _turn(
                    "good-tool", model_id=ScriptedTurnAdapter.model_id, calls=(good,)
                ),
                _turn(
                    "corrected-complete",
                    model_id=ScriptedTurnAdapter.model_id,
                    conclusion=AgentRunConclusion(
                        "candidate_completed",
                        "The corrected Tool Call completed.",
                    ),
                ),
            )
        )
        bridge = _LoopBridge()
        result = OrdivonAgentLoop(
            adapter,
            bridge,
            budget=RunBudget(4, 4, 64_000, 10_000, 1_000, 0, 1),
            clock_ms=_Clock(),
        ).run(
            harness_run_id="harness-run:r2-r3-tool-correction",
            assignment_id="assignment:r2-r3-tool-correction",
            context_digest=canonical_digest({"context": "tool-correction"}),
            initial_messages=({"role": "user", "content": "inspect"},),
        )

        self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
        self.assertEqual(bridge.attempts, 2)
        self.assertEqual(bridge.effects, 1)
        self.assertEqual(result.usage["toolCorrections"], 1)
        rejected = adapter.requests[1].messages[-1]
        self.assertEqual(rejected["role"], "tool")
        self.assertEqual(rejected["observation"]["status"], "rejected")
        self.assertTrue(rejected["observation"]["content"]["error"]["safeToCorrect"])

    def test_token_hard_limit_blocks_tool_effect(self) -> None:
        call = AgentToolCall(
            "tool-call:r2-r3:token-effect",
            "read_workspace",
            {"relativePath": "README.md"},
        )
        adapter = ScriptedTurnAdapter(
            (
                _turn(
                    "over-token-limit",
                    model_id=ScriptedTurnAdapter.model_id,
                    calls=(call,),
                    usage={"total_tokens": 101},
                ),
            )
        )
        bridge = _LoopBridge()
        result = OrdivonAgentLoop(
            adapter,
            bridge,
            budget=RunBudget(2, 2, 64_000, 10_000, 100, 0, 0),
            clock_ms=_Clock(),
        ).run(
            harness_run_id="harness-run:r2-r3-token-limit",
            assignment_id="assignment:r2-r3-token-limit",
            context_digest=canonical_digest({"context": "token-limit"}),
            initial_messages=({"role": "user", "content": "inspect"},),
        )

        self.assertEqual(result.stop_code, RunStopCode.BUDGET_EXHAUSTED)
        self.assertEqual(result.usage["totalTokens"], 101)
        self.assertEqual(bridge.attempts, 0)
        self.assertEqual(bridge.effects, 0)

    def test_run_handle_stream_matches_canonical_trace(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            HostStorage(directory) as storage,
        ):
            clock = _clock()
            _create_task(storage, clock)
            runner = HarnessRunner(
                HarnessHost(storage, clock_ms=clock),
                runtime=_RecoveryRuntime(),
                adapter=ScriptedTurnAdapter((_completion("r2-r3-stream"),)),
            )

            handle = runner.start(_plan())
            events = tuple(handle.iter_events(timeout=5))
            result = handle.result(5)

            self.assertEqual(events, result.loop_result.trace.events)
            self.assertEqual(events[0].kind, "run_started")
            self.assertEqual(events[-1].kind, "run_stopped")

    def test_patch_response_loss_replays_exact_request_once(self) -> None:
        runtime = _PatchRuntime()
        catalog = discover_harness_runtime_catalog(runtime)
        self.assertIn(
            "patch_workspace",
            {definition.name for definition in catalog.model_tools},
        )
        bridge = RuntimeToolBridge(
            _committed(runtime),
            harness_run_id="harness-run:r2-r3-patch-replay",
            runtime=runtime,
        )
        observation = bridge.execute(
            AgentToolCall(
                "tool-call:r2-r3:patch-replay",
                "patch_workspace",
                {
                    "files": [
                        {
                            "relativePath": "README.md",
                            "expectedDigest": canonical_digest("before"),
                            "edits": [
                                {
                                    "range": {
                                        "start": {"line": 1, "column": 0},
                                        "end": {"line": 1, "column": 6},
                                    },
                                    "expectedText": "before",
                                    "replacement": "after",
                                }
                            ],
                        }
                    ]
                },
            ),
            step_id="turn-1-tool-1",
        )

        self.assertEqual(observation.status, "observed")
        self.assertTrue(observation.reconciled)
        self.assertEqual(runtime.physical_effects, 1)
        patch_calls = [item for item in runtime.calls if item[0] == "workspace.patch"]
        self.assertEqual(len(patch_calls), 2)
        self.assertEqual(
            canonical_digest(patch_calls[0][1]),
            canonical_digest(patch_calls[1][1]),
        )

    def test_patch_restart_reconciles_receipt_without_redispatch(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            HostStorage(directory) as storage,
        ):
            clock = _clock()
            _create_task(storage, clock)
            runtime = _CrashPatchRuntime()
            grant = ToolGrant(
                tool_grant_id="tool-grant:r2-r3:patch",
                allowed_tools=("patch_workspace",),
                mutate_path_rules=("README.md",),
            )
            host, committed, _, _ = _assign(
                storage,
                clock,
                runtime,
                grant=grant,
                workspace_id="workspace:r2-r3:patch-restart",
            )
            assert committed.native_run_contract is not None
            run_store = HostHarnessRunStore(host, committed)
            bridge = RuntimeToolBridge(
                committed,
                harness_run_id=committed.native_run_contract.harness_run_id,
                runtime=runtime,
                run_store=run_store,
            )
            bridge.bind_run_state(
                messages=({"role": "user", "content": "patch"},),
                observations=(),
                remaining_budget={
                    "modelCalls": 4,
                    "toolCalls": 4,
                    "observationBytes": 64_000,
                    "wallTimeMs": 10_000,
                    "totalTokens": 1_000,
                    "modelRetries": 0,
                    "toolCorrections": 1,
                },
                requested_model_id="model:r2-r3",
                effective_model_id=None,
            )
            call = AgentToolCall(
                "tool-call:r2-r3:patch-crash",
                "patch_workspace",
                {
                    "files": [
                        {
                            "relativePath": "README.md",
                            "expectedDigest": canonical_digest("before"),
                            "edits": [
                                {
                                    "range": {
                                        "start": {"line": 1, "column": 0},
                                        "end": {"line": 1, "column": 6},
                                    },
                                    "expectedText": "before",
                                    "replacement": "after",
                                }
                            ],
                        }
                    ]
                },
            )
            with self.assertRaises(_InjectedCrash):
                bridge.execute_with_control(
                    call,
                    step_id="turn-1-tool-1",
                    turn_id="turn:r2-r3:patch-crash",
                    control=ExecutionControl(
                        cancellation=CancellationToken(),
                        deadline=RunDeadline.after(10_000),
                    ),
                )

            recovered_committed = bridge.committed
            recovered_store = HostHarnessRunStore(host, recovered_committed)
            recovered_bridge = RuntimeToolBridge(
                recovered_committed,
                harness_run_id=(
                    recovered_committed.native_run_contract.harness_run_id
                    if recovered_committed.native_run_contract is not None
                    else ""
                ),
                runtime=runtime,
                run_store=recovered_store,
            )
            observation = recovered_bridge.reconcile_current_tool_step()

            self.assertEqual(observation.status, "observed")
            self.assertTrue(observation.reconciled)
            self.assertEqual(runtime.physical_effects, 1)
            self.assertEqual(
                len([item for item in runtime.calls if item[0] == "workspace.patch"]),
                1,
            )
            self.assertEqual(
                len(
                    [item for item in runtime.calls if item[0] == "workspace.patch.get"]
                ),
                1,
            )
            self.assertTrue(recovered_store.load_current_tool_step().receipt.terminal)

    def test_patch_capability_must_be_exposed_as_a_pair(self) -> None:
        with self.assertRaisesRegex(RuntimeProtocolError, "must expose"):
            discover_harness_runtime_catalog(_PartialPatchRuntime())

    def test_zero_retry_budgets_round_trip_through_assignment(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            HostStorage(directory) as storage,
        ):
            clock = _clock()
            _create_task(storage, clock)
            runner = HarnessRunner(
                HarnessHost(storage, clock_ms=clock),
                runtime=_RecoveryRuntime(),
                adapter=ScriptedTurnAdapter((_completion("unused"),)),
            )
            plan = _plan()
            plan = type(plan)(
                task_contract=plan.task_contract,
                context_blocks=plan.context_blocks,
                workspace_ref=plan.workspace_ref,
                tool_grant=_grant(),
                token_budget=plan.token_budget,
                budget=RunBudget(4, 4, 64_000, 10_000, 1_000, 0, 0),
                source_ref=plan.source_ref,
                source_digest=plan.source_digest,
                prior_artifact_refs=plan.prior_artifact_refs,
                required_capabilities=plan.required_capabilities,
                deadline_ms=plan.deadline_ms,
                completion_mode=plan.completion_mode,
            )
            committed = runner.prepare(plan)
            decoded = runner._budget_from_assignment(committed)

            self.assertEqual(decoded.max_model_retries, 0)
            self.assertEqual(decoded.max_tool_corrections, 0)


if __name__ == "__main__":
    unittest.main()
