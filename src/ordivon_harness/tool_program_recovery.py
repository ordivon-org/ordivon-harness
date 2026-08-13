"""Pure restart reconstruction for Harness-native ToolProgram actions.

This module performs no Tool execution and owns no durable state.  It derives
exact inner Tool Call identities/arguments from one immutable
``HarnessToolProgramAction`` plus an exact durable observation prefix.  The same
projection can therefore be used before live integration to prove that restart
semantics do not require a second program ledger.
"""

from __future__ import annotations

from dataclasses import dataclass

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from .agent_tool_observation import HarnessToolObservation
from .ordivon.model import AgentToolCall, AgentToolDefinition
from .ordivon.tool_bridge import ToolBridge
from .tool_program import (
    HarnessToolProgramAction,
    HarnessToolProgramResult,
    _resolve_template,
)


def _action_token(action: HarnessToolProgramAction) -> str:
    return canonical_digest(
        {
            "actionCallId": action.action_call_id,
            "programDigest": action.program.digest,
        }
    )[7:31]


def derive_tool_program_inner_call(
    action: HarnessToolProgramAction,
    step_index: int,
    prior_observations: tuple[HarnessToolObservation, ...],
) -> AgentToolCall:
    """Derive one exact inner Tool Call from an observed contiguous prefix."""

    if type(step_index) is not int or not 0 <= step_index < len(action.program.steps):
        raise ValueError("ToolProgram step index is outside the program")
    if len(prior_observations) != step_index:
        raise ValueError("ToolProgram prior observation count differs from step index")

    token = _action_token(action)
    by_step: dict[str, HarnessToolObservation] = {}
    for index, observation in enumerate(prior_observations):
        step = action.program.steps[index]
        expected_id = f"tool-call:program:{token}:{index + 1}"
        if observation.tool_call_id != expected_id or observation.tool_name != step.tool_name:
            raise ValueError(
                "ToolProgram durable observation differs from derived inner Tool Call"
            )
        if observation.status != "observed":
            raise ValueError(
                "ToolProgram cannot derive a later step after a non-observed outcome"
            )
        by_step[step.step_id] = observation

    step = action.program.steps[step_index]
    resolved_arguments = _resolve_template(step.arguments, by_step)
    if not isinstance(resolved_arguments, dict):
        raise ValueError("ToolProgram step arguments must resolve to an object")
    return AgentToolCall(
        tool_call_id=f"tool-call:program:{token}:{step_index + 1}",
        name=step.tool_name,
        arguments=resolved_arguments,
    )


def derive_tool_program_step_id(
    action: HarnessToolProgramAction,
    step_index: int,
    *,
    step_prefix: str,
) -> str:
    if (
        not isinstance(step_prefix, str)
        or not step_prefix
        or step_prefix != step_prefix.strip()
        or len(step_prefix.encode("utf-8")) > 240
    ):
        raise ValueError("ToolProgram step prefix must be non-empty, trimmed and bounded")
    if type(step_index) is not int or not 0 <= step_index < len(action.program.steps):
        raise ValueError("ToolProgram step index is outside the program")
    step = action.program.steps[step_index]
    return (
        f"{step_prefix}:program:{_action_token(action)}:"
        f"{step_index + 1}:{step.step_id}"
    )


@dataclass(frozen=True, slots=True)
class HarnessToolProgramRecoveryProjection:
    """Exact derived restart state: either next inner Call or terminal result."""

    action_digest: str
    observations: tuple[HarnessToolObservation, ...]
    next_call: AgentToolCall | None
    terminal_result: HarnessToolProgramResult | None

    def __post_init__(self) -> None:
        if (self.next_call is None) == (self.terminal_result is None):
            raise ValueError(
                "ToolProgram recovery projection requires exactly one next Call or terminal result"
            )

    @property
    def terminal(self) -> bool:
        return self.terminal_result is not None

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-tool-program-recovery-projection",
            "truthRole": "derived-restart-projection",
            "actionDigest": self.action_digest,
            "observations": [item.to_dict() for item in self.observations],
            "nextCall": None if self.next_call is None else self.next_call.to_dict(),
            "terminalResult": (
                None if self.terminal_result is None else self.terminal_result.to_dict()
            ),
        }
        validate_json_value(value)
        return value


def recover_tool_program_action(
    action: HarnessToolProgramAction,
    observations: tuple[HarnessToolObservation, ...],
) -> HarnessToolProgramRecoveryProjection:
    """Reconstruct exact next work or terminal result without executing a Tool."""

    if len(observations) > len(action.program.steps):
        raise ValueError("ToolProgram durable observation prefix exceeds program length")

    observed_prefix: list[HarnessToolObservation] = []
    for index, observation in enumerate(observations):
        expected = derive_tool_program_inner_call(
            action,
            index,
            tuple(observed_prefix),
        )
        if (
            observation.tool_call_id != expected.tool_call_id
            or observation.tool_name != expected.name
        ):
            raise ValueError(
                "ToolProgram durable observation differs from derived inner Tool Call"
            )
        observed_prefix.append(observation)
        if observation.status != "observed":
            if index != len(observations) - 1:
                raise ValueError(
                    "ToolProgram durable evidence continues after terminal inner outcome"
                )
            result = HarnessToolProgramResult(
                program_digest=action.program.digest,
                status=observation.status,
                observations=tuple(observed_prefix),
                output={},
            )
            return HarnessToolProgramRecoveryProjection(
                action_digest=action.digest,
                observations=tuple(observed_prefix),
                next_call=None,
                terminal_result=result,
            )

    if len(observed_prefix) == len(action.program.steps):
        by_step = {
            step.step_id: observation
            for step, observation in zip(
                action.program.steps,
                observed_prefix,
                strict=True,
            )
        }
        output = _resolve_template(action.program.outputs, by_step)
        if not isinstance(output, dict):
            raise ValueError("ToolProgram outputs must resolve to an object")
        result = HarnessToolProgramResult(
            program_digest=action.program.digest,
            status="completed",
            observations=tuple(observed_prefix),
            output=output,
        )
        return HarnessToolProgramRecoveryProjection(
            action_digest=action.digest,
            observations=tuple(observed_prefix),
            next_call=None,
            terminal_result=result,
        )

    return HarnessToolProgramRecoveryProjection(
        action_digest=action.digest,
        observations=tuple(observed_prefix),
        next_call=derive_tool_program_inner_call(
            action,
            len(observed_prefix),
            tuple(observed_prefix),
        ),
        terminal_result=None,
    )


class HarnessToolProgramActionExecutor:
    """Execute a native ToolProgram action through one existing ToolBridge."""

    def __init__(
        self,
        bridge: ToolBridge,
        admitted_tools: tuple[AgentToolDefinition, ...],
    ) -> None:
        names = [definition.name for definition in admitted_tools]
        if len(names) != len(set(names)):
            raise ValueError("ToolProgram admitted Tool names must be unique")
        self.bridge = bridge
        self.admitted_tools = frozenset(names)

    def execute(
        self,
        action: HarnessToolProgramAction,
        *,
        remaining_tool_calls: int,
        step_prefix: str,
    ) -> HarnessToolProgramResult:
        if type(remaining_tool_calls) is not int or remaining_tool_calls < 0:
            raise ValueError("ToolProgram remaining Tool budget must be non-negative")
        if action.physical_tool_calls > remaining_tool_calls:
            raise ValueError("ToolProgram exceeds remaining Tool Call budget")
        denied = sorted(
            {step.tool_name for step in action.program.steps} - self.admitted_tools
        )
        if denied:
            raise ValueError(
                "ToolProgram references Tools not admitted on the exact turn: "
                + ", ".join(denied)
            )

        observations: list[HarnessToolObservation] = []
        for index in range(len(action.program.steps)):
            call = derive_tool_program_inner_call(
                action,
                index,
                tuple(observations),
            )
            observation = self.bridge.execute(
                call,
                step_id=derive_tool_program_step_id(
                    action,
                    index,
                    step_prefix=step_prefix,
                ),
            )
            if (
                observation.tool_call_id != call.tool_call_id
                or observation.tool_name != call.name
            ):
                raise ValueError(
                    "ToolProgram bridge returned an observation for a different Tool Call"
                )
            observations.append(observation)
            if observation.status != "observed":
                return HarnessToolProgramResult(
                    program_digest=action.program.digest,
                    status=observation.status,
                    observations=tuple(observations),
                    output={},
                )

        projection = recover_tool_program_action(action, tuple(observations))
        assert projection.terminal_result is not None
        return projection.terminal_result


__all__ = [
    "HarnessToolProgramActionExecutor",
    "HarnessToolProgramRecoveryProjection",
    "derive_tool_program_inner_call",
    "derive_tool_program_step_id",
    "recover_tool_program_action",
]
