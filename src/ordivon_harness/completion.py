from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from anc_canonical import (
    JsonValue,
    canonical_bytes,
    canonical_digest,
    loads_strict,
    validate_json_value,
)

from .core_contracts import STRUCTURED_COMPLETION_MODE, HarnessRunContract
from .ordivon.model import AgentRunConclusion
from .structured_result_conformance import (
    structured_result_conformance_policy,
    validate_structured_result_instance,
)

_MAX_RESULT_SCHEMA_BYTES = 65_536
_MAX_LEGACY_RESULT_SUMMARY_BYTES = 8_000


def _json_projection(value: Any) -> JsonValue:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("completion schema object keys must be strings")
        projected = {key: _json_projection(item) for key, item in value.items()}
        validate_json_value(projected)
        return projected
    if isinstance(value, (list, tuple)):
        projected_list = [_json_projection(item) for item in value]
        validate_json_value(projected_list)
        return projected_list
    validate_json_value(value)
    return value


def structured_completion_result_schema(
    completion_contract: Mapping[str, Any],
) -> dict[str, JsonValue] | None:
    """Return the caller-owned Provider result schema for the supported structured mode."""
    mode = completion_contract.get("mode")
    if mode != STRUCTURED_COMPLETION_MODE:
        return None
    raw_schema = completion_contract.get("resultSchema")
    projected = _json_projection(raw_schema)
    if not isinstance(projected, dict):
        raise ValueError("structured completion resultSchema must be an object")
    if len(canonical_bytes(projected)) > _MAX_RESULT_SCHEMA_BYTES:
        raise ValueError("structured completion resultSchema exceeds 65536 canonical bytes")
    return projected


def structured_completion_contract_digest(
    completion_contract: Mapping[str, Any],
) -> str | None:
    if structured_completion_result_schema(completion_contract) is None:
        return None
    projected = _json_projection(completion_contract)
    assert isinstance(projected, dict)
    return canonical_digest(projected)


def encode_structured_completion_result(
    completion_contract: Mapping[str, Any], result: JsonValue
) -> str:
    """Encode only a legacy summary-sized result; current writers use the carrier."""
    if structured_completion_result_schema(completion_contract) is None:
        raise ValueError("Harness completion Contract is not structured-result-v1")
    validate_json_value(result)
    encoded = canonical_bytes(result)
    if len(encoded) > _MAX_LEGACY_RESULT_SUMMARY_BYTES:
        raise ValueError(
            "structured result does not fit the legacy conclusion summary; "
            "use AgentStructuredResult"
        )
    return encoded.decode("utf-8")


def _structured_result_value(conclusion: AgentRunConclusion) -> JsonValue:
    carrier = conclusion.structured_result
    if carrier is not None:
        return carrier.value
    # Backward compatibility for terminal records created before the dedicated
    # carrier existed. New structured Provider conclusions never use summary as
    # the result transport.
    value = loads_strict(conclusion.summary.encode("utf-8"))
    validate_json_value(value)
    return value


def structured_completion_conclusion_validator(
    completion_contract: Mapping[str, Any],
) -> Callable[[AgentRunConclusion], None] | None:
    """Return the Contract-bound local structural validator when one is admitted."""
    if structured_completion_result_schema(completion_contract) is None:
        return None
    if structured_result_conformance_policy(completion_contract) is None:
        return None

    def validate(conclusion: AgentRunConclusion) -> None:
        value = _structured_result_value(conclusion)
        validate_structured_result_instance(completion_contract, value)

    return validate


def decode_structured_completion_result(
    contract: HarnessRunContract, conclusion: AgentRunConclusion
) -> JsonValue:
    """Decode the result; structural conformance is local only under an explicit policy."""
    if structured_completion_result_schema(contract.completion_contract) is None:
        raise ValueError("Harness Run Contract is not structured-result-v1")
    value = _structured_result_value(conclusion)
    validate_structured_result_instance(contract.completion_contract, value)
    return value


__all__ = [
    "STRUCTURED_COMPLETION_MODE",
    "decode_structured_completion_result",
    "encode_structured_completion_result",
    "structured_completion_conclusion_validator",
    "structured_completion_contract_digest",
    "structured_completion_result_schema",
]
