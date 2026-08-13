"""Privacy-aware durable evidence types for Harness ToolProgram recovery."""

from __future__ import annotations

from dataclasses import dataclass

from anc_canonical import JsonValue, validate_json_value

from .agent_tool_observation import HarnessToolObservation
from .ordivon.model import AgentToolCall
from .protocol import HarnessToolStepIntent, HarnessToolStepReceipt
from .tool_program import HarnessToolProgramAction, HarnessToolProgramResult
from .tool_program_recovery import _action_token, recover_tool_program_action


@dataclass(frozen=True, slots=True)
class HarnessToolProgramDurableStepEvidence:
    intent: HarnessToolStepIntent
    receipt: HarnessToolStepReceipt
    observation: HarnessToolObservation | None

    def __post_init__(self) -> None:
        if self.receipt.intent_digest != self.intent.digest:
            raise ValueError("ToolProgram durable Receipt differs from its Intent")
        if self.receipt.tool_call_id != self.intent.tool_call_id:
            raise ValueError("ToolProgram durable Receipt Tool Call differs")
        if self.observation is not None and (
            self.observation.tool_call_id != self.intent.tool_call_id
            or self.observation.tool_name != self.intent.tool_name
            or self.receipt.observation_digest != self.observation.digest
        ):
            raise ValueError("ToolProgram durable Observation differs from Intent/Receipt")

    def to_projection(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "intentDigest": self.intent.digest,
            "receiptDigest": self.receipt.digest,
            "toolCallId": self.intent.tool_call_id,
            "toolName": self.intent.tool_name,
            "status": self.receipt.status.value,
            "observationDigest": self.receipt.observation_digest,
            "contentAvailable": self.observation is not None,
            "reconciled": self.receipt.reconciled,
        }
        validate_json_value(value)
        return value


@dataclass(frozen=True, slots=True)
class HarnessToolProgramDurableRecoveryProjection:
    action_digest: str
    evidence: tuple[HarnessToolProgramDurableStepEvidence, ...]
    disposition: str
    next_call: AgentToolCall | None = None
    terminal_result: HarnessToolProgramResult | None = None
    recovery_reason: str | None = None

    def __post_init__(self) -> None:
        if self.disposition not in {"ready-next", "terminal", "recovery-required"}:
            raise ValueError("unsupported ToolProgram durable recovery disposition")
        present = (
            self.next_call is not None,
            self.terminal_result is not None,
            self.recovery_reason is not None,
        )
        expected = {
            "ready-next": (True, False, False),
            "terminal": (False, True, False),
            "recovery-required": (False, False, True),
        }[self.disposition]
        if present != expected:
            raise ValueError("ToolProgram durable recovery fields differ from disposition")

    @property
    def terminal(self) -> bool:
        return self.disposition == "terminal"

    @property
    def recovery_required(self) -> bool:
        return self.disposition == "recovery-required"


def recover_tool_program_from_durable_evidence(
    action: HarnessToolProgramAction,
    evidence: tuple[HarnessToolProgramDurableStepEvidence, ...],
) -> HarnessToolProgramDurableRecoveryProjection:
    """Recover without confusing privacy-redacted content with absent effects."""

    if len(evidence) > len(action.program.steps):
        raise ValueError("ToolProgram durable evidence exceeds program length")

    token = _action_token(action)
    observations: list[HarnessToolObservation] = []
    content_missing = False
    for index, item in enumerate(evidence):
        step = action.program.steps[index]
        expected_id = f"tool-call:program:{token}:{index + 1}"
        if item.intent.tool_call_id != expected_id or item.intent.tool_name != step.tool_name:
            raise ValueError(
                "ToolProgram durable Intent differs from action-bound inner identity"
            )

        # As long as every preceding observation body is available, the immutable
        # action is sufficient to derive this exact Tool Call.  Verify that the
        # already-durable Intent actually committed to those same bytes.  Once a
        # privacy boundary removes an observation body, later data-dependent calls
        # cannot be re-derived; their Intent/Receipt still proves the effect identity
        # and terminal state, but not the missing arguments.
        if not content_missing:
            from .tool_program_recovery import derive_tool_program_inner_call

            expected_call = derive_tool_program_inner_call(
                action,
                index,
                tuple(observations),
            )
            if item.intent.tool_call_digest != expected_call.digest:
                raise ValueError(
                    "ToolProgram durable Intent Tool Call digest differs from action"
                )

        if not item.receipt.terminal:
            return HarnessToolProgramDurableRecoveryProjection(
                action_digest=action.digest,
                evidence=evidence,
                disposition="recovery-required",
                recovery_reason="tool-step-nonterminal",
            )
        if item.receipt.status.value != "observed" and index != len(evidence) - 1:
            raise ValueError(
                "ToolProgram durable evidence continues after terminal inner outcome"
            )
        if item.observation is None:
            content_missing = True
            continue
        if item.observation.status != item.receipt.status.value:
            raise ValueError(
                "ToolProgram durable Observation status differs from Receipt"
            )
        if not content_missing:
            observations.append(item.observation)

    if content_missing:
        return HarnessToolProgramDurableRecoveryProjection(
            action_digest=action.digest,
            evidence=evidence,
            disposition="recovery-required",
            recovery_reason="tool-observation-content-unavailable",
        )

    recovered = recover_tool_program_action(action, tuple(observations))
    if recovered.terminal_result is not None:
        return HarnessToolProgramDurableRecoveryProjection(
            action_digest=action.digest,
            evidence=evidence,
            disposition="terminal",
            terminal_result=recovered.terminal_result,
        )
    assert recovered.next_call is not None
    return HarnessToolProgramDurableRecoveryProjection(
        action_digest=action.digest,
        evidence=evidence,
        disposition="ready-next",
        next_call=recovered.next_call,
    )


__all__ = [
    "HarnessToolProgramDurableRecoveryProjection",
    "HarnessToolProgramDurableStepEvidence",
    "recover_tool_program_from_durable_evidence",
]
