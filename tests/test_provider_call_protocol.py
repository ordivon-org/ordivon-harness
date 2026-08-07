from __future__ import annotations

from dataclasses import replace
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.protocol import (
    HarnessProviderCallFailureReceipt,
    HarnessProviderCallRecord,
    HarnessProviderCallSource,
    HarnessProviderCallStatus,
)
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    AgentToolCall,
    AgentToolDefinition,
    AgentTurnAdapterError,
    AgentTurnDispatchSafety,
    AgentTurnFailureCode,
    AgentTurnRequest,
    AgentTurnResult,
)
from ordivon_harness.protocol import HarnessProtocolError


def _digest(label: str) -> str:
    return canonical_digest({"fixture": label})


def _initial_record(
    source_kind: HarnessProviderCallSource = HarnessProviderCallSource.ASSIGNMENT,
) -> HarnessProviderCallRecord:
    return HarnessProviderCallRecord(
        record_id="harness-provider-call-record:fixture:claimed:g1",
        provider_call_id="provider-call:fixture:turn-1",
        task_id="task:fixture",
        harness_run_id="harness-run:fixture",
        assignment_id="assignment:fixture:g1",
        assignment_generation=1,
        assignment_digest=_digest("assignment"),
        source_kind=source_kind,
        source_digest=_digest(f"{source_kind.value}-source"),
        source_object_digest=_digest(f"{source_kind.value}-source-object"),
        state_object_digest=_digest(f"{source_kind.value}-run-state-object"),
        turn_id="turn:fixture:1",
        turn_sequence=1,
        request_digest=_digest("request"),
        provider_request_digest=_digest("provider-request"),
        adapter_id="ordivon.fixture-adapter.v1",
        requested_model_id="fixture-model",
        holder_id="holder:fixture:a",
        claim_generation=1,
        status=HarnessProviderCallStatus.CLAIMED,
        result_digest=None,
        result_object_digest=None,
        failure_digest=None,
        failure_object_digest=None,
        previous_record_digest=None,
        issued_at_ms=1_000,
        expires_at_ms=31_000,
        recorded_at_ms=1_000,
    )


class HarnessProviderCallRecordTests(unittest.TestCase):
    def test_assignment_claim_round_trips_with_stable_digest(self) -> None:
        record = _initial_record()

        decoded = HarnessProviderCallRecord.from_dict(record.to_dict())

        self.assertEqual(decoded, record)
        self.assertEqual(decoded.digest, canonical_digest(record.to_dict()))
        self.assertEqual(decoded.source_kind, HarnessProviderCallSource.ASSIGNMENT)
        self.assertEqual(
            decoded.state_object_digest,
            _digest("assignment-run-state-object"),
        )

    def test_snapshot_transition_chain_round_trips(self) -> None:
        claimed = _initial_record(HarnessProviderCallSource.SNAPSHOT)
        dispatching = replace(
            claimed,
            record_id="harness-provider-call-record:fixture:dispatching:g1",
            status=HarnessProviderCallStatus.DISPATCHING,
            previous_record_digest=claimed.digest,
            recorded_at_ms=1_001,
        )
        completed = replace(
            dispatching,
            record_id="harness-provider-call-record:fixture:completed:g1",
            status=HarnessProviderCallStatus.COMPLETED,
            result_digest=_digest("result"),
            result_object_digest=_digest("result-object"),
            previous_record_digest=dispatching.digest,
            recorded_at_ms=1_002,
        )
        failed = replace(
            dispatching,
            record_id="harness-provider-call-record:fixture:failed:g1",
            status=HarnessProviderCallStatus.FAILED,
            failure_digest=_digest("provider-rejection"),
            failure_object_digest=_digest("provider-rejection-object"),
            previous_record_digest=dispatching.digest,
            recorded_at_ms=1_002,
        )
        unknown = replace(
            dispatching,
            record_id="harness-provider-call-record:fixture:unknown:g1",
            status=HarnessProviderCallStatus.UNKNOWN,
            failure_digest=_digest("ambiguous-dispatch"),
            failure_object_digest=_digest("ambiguous-dispatch-object"),
            previous_record_digest=dispatching.digest,
            recorded_at_ms=1_002,
        )
        reclaimed = replace(
            claimed,
            record_id="harness-provider-call-record:fixture:claimed:g2",
            holder_id="holder:fixture:b",
            claim_generation=2,
            previous_record_digest=completed.digest,
            issued_at_ms=32_000,
            expires_at_ms=62_000,
            recorded_at_ms=32_000,
        )

        for record in (claimed, dispatching, completed, failed, unknown, reclaimed):
            with self.subTest(status=record.status, generation=record.claim_generation):
                self.assertEqual(
                    HarnessProviderCallRecord.from_dict(record.to_dict()),
                    record,
                )

    def test_generation_one_claim_may_link_to_a_completed_source_chain(self) -> None:
        claimed = _initial_record()
        replacement = replace(
            claimed,
            record_id="harness-provider-call-record:fixture:replacement:g1",
            previous_record_digest=_digest("previous-completed-record"),
        )

        self.assertEqual(
            HarnessProviderCallRecord.from_dict(replacement.to_dict()),
            replacement,
        )

    def test_malformed_records_are_rejected(self) -> None:
        claimed = _initial_record()
        dispatching = replace(
            claimed,
            record_id="harness-provider-call-record:fixture:dispatching:g1",
            status=HarnessProviderCallStatus.DISPATCHING,
            previous_record_digest=claimed.digest,
        )
        completed = replace(
            dispatching,
            record_id="harness-provider-call-record:fixture:completed:g1",
            status=HarnessProviderCallStatus.COMPLETED,
            result_digest=_digest("result"),
            result_object_digest=_digest("result-object"),
            previous_record_digest=dispatching.digest,
        )

        extra_field = claimed.to_dict()
        extra_field["unexpected"] = True
        invalid_kind = claimed.to_dict()
        invalid_kind["kind"] = "ordivon.wrong"
        invalid_source = claimed.to_dict()
        invalid_source["sourceKind"] = "checkpoint"
        invalid_status = claimed.to_dict()
        invalid_status["status"] = "sent"
        invalid_identity = claimed.to_dict()
        invalid_identity["providerCallId"] = "model-call:fixture"
        boolean_sequence = claimed.to_dict()
        boolean_sequence["turnSequence"] = True
        invalid_expiry = claimed.to_dict()
        invalid_expiry["expiresAtMs"] = invalid_expiry["issuedAtMs"]
        invalid_provider_request = claimed.to_dict()
        invalid_provider_request["providerRequestDigest"] = "sha256:UPPER"
        assignment_without_state = claimed.to_dict()
        assignment_without_state["stateObjectDigest"] = None
        snapshot_without_state = claimed.to_dict()
        snapshot_without_state["sourceKind"] = "snapshot"
        snapshot_without_state["stateObjectDigest"] = None
        completed_without_result = completed.to_dict()
        completed_without_result["resultDigest"] = None
        claim_with_result = claimed.to_dict()
        claim_with_result["resultDigest"] = _digest("unexpected-result")
        claim_with_failure = claimed.to_dict()
        claim_with_failure["failureDigest"] = _digest("unexpected-failure")
        failed_without_object = dispatching.to_dict()
        failed_without_object["status"] = "failed"
        failed_without_object["failureDigest"] = _digest("failure")
        failure_object_without_digest = dispatching.to_dict()
        failure_object_without_digest["status"] = "failed"
        failure_object_without_digest["failureObjectDigest"] = _digest(
            "failure-object"
        )
        unknown_without_failure = dispatching.to_dict()
        unknown_without_failure["status"] = "unknown"
        transition_without_previous = dispatching.to_dict()
        transition_without_previous["previousRecordDigest"] = None
        reclaim_without_previous = claimed.to_dict()
        reclaim_without_previous["claimGeneration"] = 2

        malformed = (
            extra_field,
            invalid_kind,
            invalid_source,
            invalid_status,
            invalid_identity,
            boolean_sequence,
            invalid_expiry,
            invalid_provider_request,
            assignment_without_state,
            snapshot_without_state,
            completed_without_result,
            claim_with_result,
            claim_with_failure,
            failed_without_object,
            failure_object_without_digest,
            unknown_without_failure,
            transition_without_previous,
            reclaim_without_previous,
        )
        for index, value in enumerate(malformed):
            with self.subTest(case=index):
                with self.assertRaises(HarnessProtocolError):
                    HarnessProviderCallRecord.from_dict(value)


class HarnessProviderCallFailureReceiptTests(unittest.TestCase):
    def test_failure_receipt_round_trips_with_a_stable_digest(self) -> None:
        receipt = HarnessProviderCallFailureReceipt(
            provider_call_id="provider-call:fixture:turn-1",
            request_digest=_digest("request"),
            provider_request_digest=_digest("provider-request"),
            failure_code="provider_transport_failed",
            dispatch_safety="pre_dispatch_safe",
            detail="connection refused before request dispatch",
        )

        decoded = HarnessProviderCallFailureReceipt.from_dict(receipt.to_dict())

        self.assertEqual(decoded, receipt)
        self.assertEqual(decoded.digest, canonical_digest(receipt.to_dict()))

    def test_failure_receipt_rejects_unbounded_or_unknown_fields(self) -> None:
        receipt = HarnessProviderCallFailureReceipt(
            provider_call_id="provider-call:fixture:turn-1",
            request_digest=_digest("request"),
            provider_request_digest=_digest("provider-request"),
            failure_code="provider_rejected",
            dispatch_safety="provider_rejected",
            detail="quota rejected",
        )
        malformed = []
        extra = receipt.to_dict()
        extra["retryable"] = True
        malformed.append(extra)
        invalid_code = receipt.to_dict()
        invalid_code["failureCode"] = "maybe"
        malformed.append(invalid_code)
        invalid_safety = receipt.to_dict()
        invalid_safety["dispatchSafety"] = "probably_safe"
        malformed.append(invalid_safety)
        oversized = receipt.to_dict()
        oversized["detail"] = "界" * 683
        malformed.append(oversized)

        for index, value in enumerate(malformed):
            with self.subTest(case=index):
                with self.assertRaises(HarnessProtocolError):
                    HarnessProviderCallFailureReceipt.from_dict(value)


class AgentTurnPersistenceModelTests(unittest.TestCase):
    def test_dispatch_digest_ignores_dynamic_dispatch_control_budgets(self) -> None:
        request = AgentTurnRequest(
            harness_run_id="harness-run:fixture",
            turn_id="turn:fixture:1",
            sequence=1,
            assignment_id="assignment:fixture:g1",
            context_digest=_digest("context"),
            tool_catalog_digest=_digest("tool-catalog"),
            messages=({"role": "user", "content": "Inspect the repository."},),
            tools=(
                AgentToolDefinition(
                    name="workspace_read",
                    description="Read a workspace file.",
                    input_schema={
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                    },
                ),
            ),
            remaining_budget={
                "modelCalls": 3,
                "toolCalls": 4,
                "modelRetries": 2,
                "wallTimeMs": 30_000,
            },
        )
        later_wall_clock = replace(
            request,
            remaining_budget={
                "modelCalls": 3,
                "toolCalls": 4,
                "modelRetries": 1,
                "wallTimeMs": 20_000,
            },
        )
        fewer_model_calls = replace(
            request,
            remaining_budget={
                "modelCalls": 2,
                "toolCalls": 4,
                "modelRetries": 2,
                "wallTimeMs": 30_000,
            },
        )

        self.assertNotEqual(request.digest, later_wall_clock.digest)
        self.assertEqual(request.dispatch_digest, later_wall_clock.dispatch_digest)
        self.assertNotEqual(request.dispatch_digest, fewer_model_calls.dispatch_digest)
        self.assertEqual(request.remaining_budget["wallTimeMs"], 30_000)

    def test_tool_call_round_trips_with_optional_provider_arguments(self) -> None:
        normalized = AgentToolCall(
            tool_call_id="tool-call:fixture:malformed",
            name="workspace_read",
            arguments={},
            argument_error="arguments were not valid JSON",
            raw_arguments_digest=_digest("raw-provider-arguments"),
            raw_arguments_preview="{broken",
        )
        ordinary = AgentToolCall(
            tool_call_id="tool-call:fixture:ordinary",
            name="workspace_read",
            arguments={"path": "README.md"},
        )

        self.assertEqual(AgentToolCall.from_dict(normalized.to_dict()), normalized)
        self.assertEqual(AgentToolCall.from_dict(ordinary.to_dict()), ordinary)

    def test_conclusion_and_results_round_trip_with_optional_effective_model(self) -> None:
        conclusion = AgentRunConclusion(
            status="needs_input",
            summary="Need the operator to select a target.",
            artifact_refs=("artifact:fixture",),
            evidence_refs=("evidence:fixture",),
            unresolved_unknowns=("target repository",),
        )
        concluded = AgentTurnResult(
            model_call_id="model-call:fixture:conclusion",
            model_id="requested-model",
            content=None,
            tool_calls=(),
            conclusion=conclusion,
            usage={"inputTokens": 10, "outputTokens": 5},
            finish_reason="tool_calls",
            raw_response_digest=_digest("conclusion-response"),
        )
        tool_result = AgentTurnResult(
            model_call_id="model-call:fixture:tool",
            model_id="requested-model",
            effective_model_id="effective-model",
            content="Inspecting the repository.",
            tool_calls=(
                AgentToolCall(
                    tool_call_id="tool-call:fixture:read",
                    name="workspace_read",
                    arguments={"path": "README.md"},
                ),
            ),
            conclusion=None,
            usage={"inputTokens": 20, "outputTokens": 8},
            finish_reason="tool_calls",
            raw_response_digest=_digest("tool-response"),
        )

        self.assertEqual(
            AgentRunConclusion.from_dict(conclusion.to_dict()),
            conclusion,
        )
        self.assertNotIn("effectiveModelId", concluded.to_dict())
        self.assertEqual(AgentTurnResult.from_dict(concluded.to_dict()), concluded)
        self.assertEqual(AgentTurnResult.from_dict(tool_result.to_dict()), tool_result)

    def test_malformed_normalized_results_are_rejected(self) -> None:
        call = AgentToolCall(
            tool_call_id="tool-call:fixture:read",
            name="workspace_read",
            arguments={"path": "README.md"},
        )
        result = AgentTurnResult(
            model_call_id="model-call:fixture:tool",
            model_id="requested-model",
            content=None,
            tool_calls=(call,),
            conclusion=None,
            usage={},
            finish_reason="tool_calls",
            raw_response_digest=_digest("tool-response"),
        )

        extra_call_field = call.to_dict()
        extra_call_field["unexpected"] = True
        partial_diagnostics = call.to_dict()
        partial_diagnostics["providerArguments"] = {
            "error": "bad",
            "rawDigest": _digest("raw"),
        }
        null_diagnostics = call.to_dict()
        null_diagnostics["providerArguments"] = None
        invalid_conclusion = AgentRunConclusion(
            "needs_input",
            "Need input.",
        ).to_dict()
        invalid_conclusion["artifactRefs"] = "artifact:not-a-list"
        extra_result_field = result.to_dict()
        extra_result_field["unexpected"] = True
        boolean_schema = result.to_dict()
        boolean_schema["schemaVersion"] = True
        object_tool_calls = result.to_dict()
        object_tool_calls["toolCalls"] = {}
        invalid_content = result.to_dict()
        invalid_content["content"] = 42
        invalid_effective_model = result.to_dict()
        invalid_effective_model["effectiveModelId"] = 42
        invalid_nested_call = result.to_dict()
        invalid_nested_call["toolCalls"] = [partial_diagnostics]

        cases = (
            (AgentToolCall.from_dict, extra_call_field),
            (AgentToolCall.from_dict, partial_diagnostics),
            (AgentToolCall.from_dict, null_diagnostics),
            (AgentRunConclusion.from_dict, invalid_conclusion),
            (AgentTurnResult.from_dict, extra_result_field),
            (AgentTurnResult.from_dict, boolean_schema),
            (AgentTurnResult.from_dict, object_tool_calls),
            (AgentTurnResult.from_dict, invalid_content),
            (AgentTurnResult.from_dict, invalid_effective_model),
            (AgentTurnResult.from_dict, invalid_nested_call),
        )
        for index, (decoder, value) in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(ValueError):
                    decoder(value)

    def test_adapter_error_defaults_to_ambiguous_dispatch(self) -> None:
        ambiguous = AgentTurnAdapterError("fixture failure")
        safe = AgentTurnAdapterError(
            "fixture pre-dispatch rejection",
            failure_code=AgentTurnFailureCode.REJECTED,
            dispatch_safety=AgentTurnDispatchSafety.PRE_DISPATCH_SAFE,
        )
        rejected = AgentTurnAdapterError(
            "fixture Provider rejection",
            dispatch_safety=AgentTurnDispatchSafety.PROVIDER_REJECTED,
        )

        self.assertEqual(
            ambiguous.dispatch_safety,
            AgentTurnDispatchSafety.DISPATCH_AMBIGUOUS,
        )
        self.assertEqual(safe.failure_code, AgentTurnFailureCode.REJECTED)
        self.assertEqual(
            safe.dispatch_safety,
            AgentTurnDispatchSafety.PRE_DISPATCH_SAFE,
        )
        self.assertEqual(
            rejected.dispatch_safety,
            AgentTurnDispatchSafety.PROVIDER_REJECTED,
        )


if __name__ == "__main__":
    unittest.main()
