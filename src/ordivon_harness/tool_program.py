"""Deterministic programmatic composition over already-admitted Harness Tools.

This module deliberately does not execute Python/shell or call Runtime directly.
A ToolProgram is a bounded linear dataflow plan. Each step resolves exact values
from *prior observed* Tool observations, becomes an ordinary ``AgentToolCall``,
and is executed by the caller-supplied existing ``ToolBridge``.

The module is advanced composition machinery, not a Tool grant, Runtime authority,
or a second recovery/store plane.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anc_canonical import JsonValue, canonical_bytes, canonical_digest, validate_json_value

from .agent_tool_observation import HarnessToolObservation
from .ordivon.model import AgentToolCall, AgentToolDefinition
from .ordivon.tool_bridge import ToolBridge

_OBSERVATION_REF_KEY = "$harnessObservationRef"
_MAX_STEPS = 32
_MAX_PATH_SEGMENTS = 16
_MAX_PROGRAM_BYTES = 131_072
_MAX_STEP_ID_BYTES = 120
_MAX_OUTPUTS = 32


def _text(value: Any, label: str, *, max_bytes: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _is_observation_ref(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {_OBSERVATION_REF_KEY}


def _parse_observation_ref(value: dict[str, Any]) -> tuple[str, tuple[str | int, ...]]:
    raw = value[_OBSERVATION_REF_KEY]
    if not isinstance(raw, dict) or set(raw) != {"stepId", "path"}:
        raise ValueError("ToolProgram observation reference fields differ")
    step_id = _text(raw["stepId"], "ToolProgram observation reference step", max_bytes=_MAX_STEP_ID_BYTES)
    path = raw["path"]
    if (
        not isinstance(path, list)
        or not path
        or len(path) > _MAX_PATH_SEGMENTS
        or any(
            (not isinstance(segment, str) or not segment or segment != segment.strip())
            if not isinstance(segment, int)
            else segment < 0
            for segment in path
        )
        or any(isinstance(segment, bool) for segment in path)
    ):
        raise ValueError("ToolProgram observation reference path is invalid")
    return step_id, tuple(path)


def observation_ref(step_id: str, *path: str | int) -> dict[str, JsonValue]:
    """Return the canonical JSON marker for one prior observation data reference.

    Paths are relative to ``HarnessToolObservation.structured_content``. The
    reference substitutes the exact JSON value at that path; string interpolation
    and arbitrary expressions are intentionally unsupported.
    """

    marker: dict[str, JsonValue] = {
        _OBSERVATION_REF_KEY: {
            "stepId": step_id,
            "path": list(path),
        }
    }
    _parse_observation_ref(marker)
    validate_json_value(marker)
    return marker


def _walk_refs(value: JsonValue) -> tuple[tuple[str, tuple[str | int, ...]], ...]:
    refs: list[tuple[str, tuple[str | int, ...]]] = []

    def walk(item: JsonValue) -> None:
        if _is_observation_ref(item):
            assert isinstance(item, dict)
            refs.append(_parse_observation_ref(item))
            return
        if isinstance(item, dict):
            for child in item.values():
                walk(child)
            return
        if isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return tuple(refs)


def _lookup_path(value: JsonValue, path: tuple[str | int, ...]) -> JsonValue:
    current: JsonValue = value
    for segment in path:
        if isinstance(segment, int):
            if not isinstance(current, list) or segment >= len(current):
                raise ValueError("ToolProgram observation reference path is unavailable")
            current = current[segment]
            continue
        if not isinstance(current, dict) or segment not in current:
            raise ValueError("ToolProgram observation reference path is unavailable")
        current = current[segment]
    validate_json_value(current)
    return current


def _resolve_template(
    value: JsonValue,
    observations: dict[str, HarnessToolObservation],
) -> JsonValue:
    if _is_observation_ref(value):
        assert isinstance(value, dict)
        step_id, path = _parse_observation_ref(value)
        observation = observations.get(step_id)
        if observation is None or observation.status != "observed":
            raise ValueError(
                "ToolProgram observation reference requires an already observed prior step"
            )
        return _lookup_path(observation.structured_content, path)
    if isinstance(value, dict):
        resolved = {key: _resolve_template(child, observations) for key, child in value.items()}
        validate_json_value(resolved)
        return resolved
    if isinstance(value, list):
        resolved_list = [_resolve_template(child, observations) for child in value]
        validate_json_value(resolved_list)
        return resolved_list
    validate_json_value(value)
    return value


@dataclass(frozen=True, slots=True)
class HarnessToolProgramStep:
    step_id: str
    tool_name: str
    arguments: dict[str, JsonValue]

    def __post_init__(self) -> None:
        _text(self.step_id, "ToolProgram step identity", max_bytes=_MAX_STEP_ID_BYTES)
        _text(self.tool_name, "ToolProgram Tool name", max_bytes=120)
        validate_json_value(self.arguments)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "stepId": self.step_id,
            "toolName": self.tool_name,
            "arguments": self.arguments,
        }


@dataclass(frozen=True, slots=True)
class HarnessToolProgram:
    steps: tuple[HarnessToolProgramStep, ...]
    outputs: dict[str, JsonValue]

    def __post_init__(self) -> None:
        if not self.steps or len(self.steps) > _MAX_STEPS:
            raise ValueError(f"ToolProgram requires 1..{_MAX_STEPS} steps")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("ToolProgram step identities must be unique")
        if len(self.outputs) > _MAX_OUTPUTS:
            raise ValueError(f"ToolProgram outputs exceed {_MAX_OUTPUTS}")
        for name in self.outputs:
            _text(name, "ToolProgram output name", max_bytes=120)
        validate_json_value(self.outputs)

        available: set[str] = set()
        for step in self.steps:
            for ref_step, _ in _walk_refs(step.arguments):
                if ref_step not in available:
                    raise ValueError(
                        "ToolProgram step may reference only an already completed prior step"
                    )
            available.add(step.step_id)
        for ref_step, _ in _walk_refs(self.outputs):
            if ref_step not in available:
                raise ValueError("ToolProgram output references an unknown step")
        if len(canonical_bytes(self.to_dict())) > _MAX_PROGRAM_BYTES:
            raise ValueError(f"ToolProgram exceeds {_MAX_PROGRAM_BYTES} canonical bytes")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-tool-program",
            "steps": [step.to_dict() for step in self.steps],
            "outputs": self.outputs,
        }
        validate_json_value(value)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "HarnessToolProgram":
        if set(value) != {"schemaVersion", "kind", "steps", "outputs"}:
            raise ValueError("HarnessToolProgram fields differ")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.harness-tool-program":
            raise ValueError("HarnessToolProgram identity is invalid")
        raw_steps = value["steps"]
        raw_outputs = value["outputs"]
        if not isinstance(raw_steps, list) or any(not isinstance(item, dict) for item in raw_steps):
            raise ValueError("HarnessToolProgram steps are invalid")
        if not isinstance(raw_outputs, dict):
            raise ValueError("HarnessToolProgram outputs are invalid")
        steps: list[HarnessToolProgramStep] = []
        for raw in raw_steps:
            if set(raw) != {"stepId", "toolName", "arguments"} or not isinstance(raw["arguments"], dict):
                raise ValueError("HarnessToolProgramStep fields are invalid")
            steps.append(
                HarnessToolProgramStep(
                    step_id=raw["stepId"],
                    tool_name=raw["toolName"],
                    arguments=dict(raw["arguments"]),
                )
            )
        return cls(steps=tuple(steps), outputs=dict(raw_outputs))


@dataclass(frozen=True, slots=True)
class HarnessToolProgramAction:
    """One Harness-native program action over already-admitted Runtime/World Tools.

    This is deliberately not ``AgentToolCall``: one action may require many
    physical Tool Calls, and accounting/recovery must continue to see every inner
    effect rather than treating the envelope as one Runtime Tool.
    """

    action_call_id: str
    program: HarnessToolProgram

    def __post_init__(self) -> None:
        _text(self.action_call_id, "ToolProgram action Call identity", max_bytes=300)
        if not isinstance(self.program, HarnessToolProgram):
            raise TypeError("ToolProgram action requires HarnessToolProgram")

    @property
    def physical_tool_calls(self) -> int:
        return len(self.program.steps)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-tool-program-action",
            "actionCallId": self.action_call_id,
            "program": self.program.to_dict(),
            "physicalToolCalls": self.physical_tool_calls,
        }
        validate_json_value(value)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "HarnessToolProgramAction":
        if set(value) != {
            "schemaVersion",
            "kind",
            "actionCallId",
            "program",
            "physicalToolCalls",
        }:
            raise ValueError("HarnessToolProgramAction fields differ")
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-tool-program-action"
        ):
            raise ValueError("HarnessToolProgramAction identity is invalid")
        raw_program = value["program"]
        if not isinstance(raw_program, dict):
            raise ValueError("HarnessToolProgramAction program is invalid")
        action = cls(
            action_call_id=value["actionCallId"],
            program=HarnessToolProgram.from_dict(raw_program),
        )
        if value["physicalToolCalls"] != action.physical_tool_calls:
            raise ValueError("HarnessToolProgramAction physical Tool count differs")
        return action


def project_tool_program_action_capability(
    *,
    admitted_tools: tuple[AgentToolDefinition, ...],
    remaining_tool_calls: int,
) -> dict[str, JsonValue]:
    """Project dormant program-composition capability without granting any Tool."""

    if type(remaining_tool_calls) is not int or remaining_tool_calls < 0:
        raise ValueError("ToolProgram capability remaining Tool budget must be non-negative")
    names = [definition.name for definition in admitted_tools]
    if len(names) != len(set(names)):
        raise ValueError("ToolProgram capability Tool names must be unique")
    value: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-tool-program-action-capability",
        "truthRole": "derived-turn-composition-capability",
        "admittedToolNames": sorted(names),
        "maxProgramSteps": min(_MAX_STEPS, remaining_tool_calls),
        "physicalToolAccounting": "one-existing-tool-budget-unit-per-program-step",
        "executionAuthority": "existing-exact-turn-tool-surface-only",
        "runtimeTool": False,
    }
    validate_json_value(value)
    return value


@dataclass(frozen=True, slots=True)
class HarnessToolProgramResult:
    program_digest: str
    status: str
    observations: tuple[HarnessToolObservation, ...]
    output: dict[str, JsonValue]

    def __post_init__(self) -> None:
        if self.status not in {
            "completed",
            "rejected",
            "unknown",
            "cancel-requested",
            "cancelled",
        }:
            raise ValueError(f"unsupported ToolProgram result status: {self.status}")
        validate_json_value(self.output)
        if self.status == "completed" and any(
            observation.status != "observed" for observation in self.observations
        ):
            raise ValueError("completed ToolProgram contains a non-observed step")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-tool-program-result",
            "programDigest": self.program_digest,
            "status": self.status,
            "observations": [observation.to_dict() for observation in self.observations],
            "output": self.output,
        }
        validate_json_value(value)
        return value

    def to_model_projection(self) -> dict[str, JsonValue]:
        """Project bounded program outcome without replaying intermediate content."""

        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-tool-program-model-projection",
            "programDigest": self.program_digest,
            "status": self.status,
            "steps": [
                {
                    "toolCallId": observation.tool_call_id,
                    "toolName": observation.tool_name,
                    "status": observation.status,
                    "observationDigest": observation.digest,
                    "runtimeJobRef": observation.runtime_job_ref,
                    "artifactRefs": [item.to_dict() for item in observation.artifact_refs],
                    "reconciled": observation.reconciled,
                }
                for observation in self.observations
            ],
            "output": self.output,
        }
        validate_json_value(value)
        return value


class HarnessToolProgramExecutor:
    """Execute one bounded ToolProgram over one exact already-admitted Tool surface."""

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
        program: HarnessToolProgram,
        *,
        remaining_tool_calls: int,
        step_prefix: str,
    ) -> HarnessToolProgramResult:
        if type(remaining_tool_calls) is not int or remaining_tool_calls < 0:
            raise ValueError("ToolProgram remaining Tool budget must be non-negative")
        _text(step_prefix, "ToolProgram step prefix", max_bytes=240)
        if len(program.steps) > remaining_tool_calls:
            raise ValueError("ToolProgram exceeds remaining Tool Call budget")
        denied = sorted({step.tool_name for step in program.steps} - self.admitted_tools)
        if denied:
            raise ValueError(
                "ToolProgram references Tools not admitted on the exact turn: "
                + ", ".join(denied)
            )

        observations_by_step: dict[str, HarnessToolObservation] = {}
        observations: list[HarnessToolObservation] = []
        token = program.digest[7:31]
        for index, step in enumerate(program.steps, start=1):
            resolved_arguments = _resolve_template(step.arguments, observations_by_step)
            if not isinstance(resolved_arguments, dict):
                raise ValueError("ToolProgram step arguments must resolve to an object")
            call = AgentToolCall(
                tool_call_id=f"tool-call:program:{token}:{index}",
                name=step.tool_name,
                arguments=resolved_arguments,
            )
            observation = self.bridge.execute(
                call,
                step_id=f"{step_prefix}:program:{token}:{index}:{step.step_id}",
            )
            if (
                observation.tool_call_id != call.tool_call_id
                or observation.tool_name != call.name
            ):
                raise ValueError("ToolProgram bridge returned an observation for a different Tool Call")
            observations.append(observation)
            observations_by_step[step.step_id] = observation
            if observation.status != "observed":
                return HarnessToolProgramResult(
                    program_digest=program.digest,
                    status=observation.status,
                    observations=tuple(observations),
                    output={},
                )

        resolved_output = _resolve_template(program.outputs, observations_by_step)
        if not isinstance(resolved_output, dict):
            raise ValueError("ToolProgram outputs must resolve to an object")
        return HarnessToolProgramResult(
            program_digest=program.digest,
            status="completed",
            observations=tuple(observations),
            output=resolved_output,
        )


__all__ = [
    "HarnessToolProgram",
    "HarnessToolProgramExecutor",
    "HarnessToolProgramResult",
    "HarnessToolProgramStep",
    "observation_ref",
]
