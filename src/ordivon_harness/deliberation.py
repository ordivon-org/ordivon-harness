from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

from anc_canonical import JsonValue, canonical_bytes, canonical_digest, validate_json_value

from .domain_tools import DomainToolBridge, DomainToolLoopPlan, DomainToolLoopRunner
from .ordivon.loop import AgentLoopResult, CancellationToken
from .ordivon.model import AgentTurnAdapter, AgentTurnRequest, AgentTurnResult


_DELIBERATION_RECORD_REVISION = "deliberation-before-tools-v1"
_RECORD_MARKER = "PRIOR_NON_AUTHORITATIVE_SELF_DELIBERATION_RECORD"


@dataclass(frozen=True, slots=True)
class NonAuthoritativeDeliberationRecord:
    """Exact identity/projection of one no-Tool cognition turn.

    The record is model cognition evidence only. It is not world truth, domain
    admission, Tool intent, or proof of strategy correctness.
    """

    context_digest: str
    request_digest: str
    result_digest: str
    adapter_id: str
    requested_model_id: str
    effective_model_id: str
    summary: str
    unresolved_unknowns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        value = self.to_dict()
        validate_json_value(value)
        if not self.context_digest.startswith("sha256:"):
            raise ValueError("deliberation Context digest must be sha256")
        if not self.request_digest.startswith("sha256:"):
            raise ValueError("deliberation request digest must be sha256")
        if not self.result_digest.startswith("sha256:"):
            raise ValueError("deliberation result digest must be sha256")
        if not self.adapter_id.strip() or not self.requested_model_id.strip():
            raise ValueError("deliberation adapter/model identity must be non-empty")
        if not self.effective_model_id.strip():
            raise ValueError("deliberation effective model identity must be non-empty")
        if not self.summary.strip():
            raise ValueError("deliberation summary must be non-empty")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.non-authoritative-deliberation-record",
            "revision": _DELIBERATION_RECORD_REVISION,
            "truthRole": "model-cognition-not-world-truth-or-domain-authority",
            "contextDigest": self.context_digest,
            "requestDigest": self.request_digest,
            "resultDigest": self.result_digest,
            "adapterId": self.adapter_id,
            "requestedModelId": self.requested_model_id,
            "effectiveModelId": self.effective_model_id,
            "summary": self.summary,
            "unresolvedUnknowns": list(self.unresolved_unknowns),
            "domainToolIntent": False,
            "domainAdmission": False,
            "externalEffect": False,
        }

    def to_model_message(self) -> dict[str, JsonValue]:
        projection = canonical_bytes(self.to_dict()).decode("utf-8")
        message: dict[str, JsonValue] = {
            "role": "user",
            "content": (
                f"{_RECORD_MARKER}\n{projection}\n\n"
                "This is your prior cognition record for the same Context. It is not world truth, "
                "not domain Tool intent, and not admission or evidence that any external effect "
                "occurred. Re-check it against the unchanged Context and use the caller-granted "
                "Tools only for the action/choice you currently endorse."
            ),
        }
        validate_json_value(message)
        return message


@dataclass(frozen=True, slots=True)
class DeliberationThenToolExecution:
    deliberation: NonAuthoritativeDeliberationRecord
    deliberation_result: AgentTurnResult
    tool_plan: DomainToolLoopPlan
    tool_result: AgentLoopResult

    @property
    def execution_digest(self) -> str:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.deliberation-then-tool-execution",
            "deliberationDigest": self.deliberation.digest,
            "toolContextDigest": self.tool_plan.context_digest,
            "toolTraceDigest": canonical_digest(self.tool_result.trace.to_dict()),
            "toolStopCode": str(
                getattr(self.tool_result.stop_code, "value", self.tool_result.stop_code)
            ),
        }
        return canonical_digest(value)


class DeliberationThenToolRunner:
    """Optionally compose one bounded no-Tool cognition turn before a domain Tool loop.

    Harness owns only sequencing, exact cognition-record identity, same-Context
    binding, and the Tool-surface transition. Domain semantics/admission/effects
    remain entirely behind the caller-supplied DomainToolBridge.

    The deliberation request and Tool plan retain their caller-supplied budgets;
    this helper does not invent or claim a new aggregate cross-phase budget.
    """

    def __init__(self, adapter: AgentTurnAdapter, bridge: DomainToolBridge) -> None:
        self.adapter = adapter
        self.bridge = bridge

    def run(
        self,
        deliberation_request: AgentTurnRequest,
        tool_plan: DomainToolLoopPlan,
        *,
        cancellation: CancellationToken | None = None,
    ) -> DeliberationThenToolExecution:
        self._validate_inputs(deliberation_request, tool_plan)
        deliberation_result = self.adapter.invoke(deliberation_request)
        record = self._record(deliberation_request, deliberation_result)
        augmented_plan = replace(
            tool_plan,
            initial_messages=(
                *tool_plan.initial_messages,
                record.to_model_message(),
            ),
        )
        tool_result = DomainToolLoopRunner(self.adapter, self.bridge).run(
            augmented_plan,
            cancellation=cancellation,
        )
        return DeliberationThenToolExecution(
            deliberation=record,
            deliberation_result=deliberation_result,
            tool_plan=augmented_plan,
            tool_result=tool_result,
        )

    def _validate_inputs(
        self,
        deliberation_request: AgentTurnRequest,
        tool_plan: DomainToolLoopPlan,
    ) -> None:
        if deliberation_request.tools:
            raise ValueError("deliberation-before-Tools request must not expose domain Tools")
        if not deliberation_request.capabilities.default:
            raise ValueError(
                "deliberation-before-Tools request must use default non-mutating Harness capabilities"
            )
        if deliberation_request.context_digest != tool_plan.context_digest:
            raise ValueError("deliberation and Tool phases must bind the same Context digest")

    def _record(
        self,
        request: AgentTurnRequest,
        result: AgentTurnResult,
    ) -> NonAuthoritativeDeliberationRecord:
        if result.tool_calls:
            raise ValueError("deliberation-before-Tools Provider result unexpectedly contains Tool Calls")
        if result.conclusion is None:
            raise ValueError("deliberation-before-Tools Provider result must contain a conclusion")
        if result.conclusion.status != "candidate_completed":
            raise ValueError(
                "deliberation-before-Tools conclusion must be candidate_completed before Tool exposure"
            )
        if result.model_id != self.adapter.model_id:
            raise ValueError("deliberation result requested model differs from runner adapter")
        return NonAuthoritativeDeliberationRecord(
            context_digest=request.context_digest,
            request_digest=request.dispatch_digest,
            result_digest=result.digest,
            adapter_id=self.adapter.adapter_id,
            requested_model_id=self.adapter.model_id,
            effective_model_id=result.effective_model,
            summary=result.conclusion.summary,
            unresolved_unknowns=result.conclusion.unresolved_unknowns,
        )


__all__ = [
    "DeliberationThenToolExecution",
    "DeliberationThenToolRunner",
    "NonAuthoritativeDeliberationRecord",
]
