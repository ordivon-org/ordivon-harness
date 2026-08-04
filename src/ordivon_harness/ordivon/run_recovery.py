"""Pure restoration and evidence helpers for durable Harness Tool batches."""

from __future__ import annotations

from dataclasses import dataclass

from anc_canonical import JsonValue, canonical_digest

from ..protocol import HarnessToolStepIntent
from .model import AgentToolCall
from .tools import ToolObservation


@dataclass(frozen=True, slots=True)
class _RecoveredToolBatch:
    intent: HarnessToolStepIntent
    calls: tuple[AgentToolCall, ...]
    pending_calls: tuple[AgentToolCall, ...]
    prior_observations: tuple[ToolObservation, ...]
    active_call: AgentToolCall

def _observation_evidence_signature(observation: ToolObservation) -> str:
    return canonical_digest(
        {
            "toolName": observation.tool_name,
            "status": observation.status,
            "structuredContent": observation.structured_content,
            "artifactRefs": [item.to_dict() for item in observation.artifact_refs],
        }
    )

def _retained_tool_calls(
    messages: list[dict[str, JsonValue]],
) -> dict[str, AgentToolCall]:
    retained: dict[str, AgentToolCall] = {}
    for message in messages:
        raw_calls = message.get("toolCalls")
        if not isinstance(raw_calls, list):
            continue
        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                continue
            tool_call_id = raw_call.get("toolCallId")
            name = raw_call.get("name")
            arguments = raw_call.get("arguments")
            if (
                not isinstance(tool_call_id, str)
                or not isinstance(name, str)
                or not isinstance(arguments, dict)
            ):
                continue
            try:
                retained[tool_call_id] = AgentToolCall(
                    tool_call_id,
                    name,
                    dict(arguments),
                )
            except (TypeError, ValueError):
                continue
    return retained

def _recover_tool_batch(
    messages: list[dict[str, JsonValue]],
    observations: list[ToolObservation],
    seen_tool_call_ids: set[str],
    intent: HarnessToolStepIntent,
) -> _RecoveredToolBatch:
    batches: list[tuple[AgentToolCall, ...]] = []
    all_call_ids: set[str] = set()
    for message in messages:
        raw_calls = message.get("toolCalls")
        if raw_calls is None:
            continue
        if (
            message.get("role") != "assistant"
            or not isinstance(raw_calls, list)
            or not raw_calls
            or any(not isinstance(item, dict) for item in raw_calls)
        ):
            raise ValueError("durable Tool batch message is invalid")
        calls = tuple(
            AgentToolCall.from_dict(dict(item))
            for item in raw_calls
            if isinstance(item, dict)
        )
        call_ids = [call.tool_call_id for call in calls]
        if (
            len(call_ids) != len(set(call_ids))
            or any(call_id in all_call_ids for call_id in call_ids)
        ):
            raise ValueError("durable Tool batch repeats a Tool Call identity")
        all_call_ids.update(call_ids)
        if intent.tool_call_id in call_ids:
            batches.append(calls)
    if len(batches) != 1:
        raise ValueError(
            "active Tool Step must identify exactly one durable assistant batch"
        )
    calls = batches[0]
    active_index = next(
        index
        for index, call in enumerate(calls)
        if call.tool_call_id == intent.tool_call_id
    )
    active_call = calls[active_index]
    if (
        active_call.name != intent.tool_name
        or active_call.digest != intent.tool_call_digest
    ):
        raise ValueError("active Tool Step differs from its durable assistant call")

    prefix = calls[: active_index + 1]
    pending = calls[active_index + 1 :]
    if any(call.tool_call_id not in seen_tool_call_ids for call in prefix) or any(
        call.tool_call_id in seen_tool_call_ids for call in pending
    ):
        raise ValueError("durable Tool batch cursor is not a contiguous seen prefix")

    observations_by_call: dict[str, ToolObservation] = {}
    batch_call_ids = {call.tool_call_id for call in calls}
    for observation in observations:
        if observation.tool_call_id not in batch_call_ids:
            continue
        if observation.tool_call_id in observations_by_call:
            raise ValueError("durable Tool batch repeats a Tool Observation")
        observations_by_call[observation.tool_call_id] = observation
    prior_observations: list[ToolObservation] = []
    for call in calls[:active_index]:
        observation = observations_by_call.get(call.tool_call_id)
        if observation is None or observation.tool_name != call.name:
            raise ValueError(
                "durable Tool batch is missing a preceding Tool Observation"
            )
        if observation.status in {"unknown", "cancel-requested", "cancelled"}:
            raise ValueError(
                "durable Tool batch advanced beyond a terminal Tool Observation"
            )
        prior_observations.append(observation)
    if any(
        call.tool_call_id in observations_by_call
        for call in calls[active_index:]
    ):
        raise ValueError(
            "durable Tool batch state contains an Observation beyond its cursor"
        )
    return _RecoveredToolBatch(
        intent=intent,
        calls=calls,
        pending_calls=pending,
        prior_observations=tuple(prior_observations),
        active_call=active_call,
    )

def _search_evidence(
    call: AgentToolCall,
    observation: ToolObservation,
) -> tuple[tuple[str, str], set[str]]:
    query = call.arguments.get("query")
    relative_path = call.arguments.get("relativePath")
    if not isinstance(query, str) or not isinstance(relative_path, str):
        return (call.digest, "."), {
            _observation_evidence_signature(observation)
        }
    raw_matches = observation.structured_content.get("matches")
    matches = (
        {
            canonical_digest(match)
            for match in raw_matches
            if isinstance(match, dict)
        }
        if isinstance(raw_matches, list)
        else {_observation_evidence_signature(observation)}
    )
    return (query, relative_path), matches

def _path_subsumes(parent: str, child: str) -> bool:
    normalized_parent = parent.rstrip("/")
    normalized_child = child.rstrip("/")
    return (
        normalized_parent in {"", "."}
        or normalized_child == normalized_parent
        or normalized_child.startswith(normalized_parent + "/")
    )
