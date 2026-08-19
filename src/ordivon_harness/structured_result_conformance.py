from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from anc_canonical import JsonValue, validate_json_value
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

LOCAL_JSON_SCHEMA_DRAFT_2020_12_PROFILE_V1 = (
    "local-json-schema-draft-2020-12-profile-v1"
)

_ALLOWED_SCHEMA_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "additionalProperties",
        "required",
        "items",
        "enum",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
    }
)
_ALLOWED_TYPE_NAMES = frozenset({"object", "array", "string", "integer", "boolean"})


def structured_result_conformance_policy(
    completion_contract: Mapping[str, Any],
) -> str | None:
    value = completion_contract.get("conformancePolicy")
    if value is None:
        return None
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError("structured completion conformancePolicy must be a non-empty string")
    if value != LOCAL_JSON_SCHEMA_DRAFT_2020_12_PROFILE_V1:
        raise ValueError(f"unsupported structured completion conformancePolicy: {value}")
    return value


def _json_projection(value: Any) -> JsonValue:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("structured completion schema object keys must be strings")
        projected = {key: _json_projection(item) for key, item in value.items()}
        validate_json_value(projected)
        return projected
    if isinstance(value, tuple):
        projected_list = [_json_projection(item) for item in value]
        validate_json_value(projected_list)
        return projected_list
    if isinstance(value, list):
        projected_list = [_json_projection(item) for item in value]
        validate_json_value(projected_list)
        return projected_list
    validate_json_value(value)
    return value


def _require_profile_schema(schema: Mapping[str, Any], *, path: str = "$resultSchema") -> None:
    unknown = sorted(set(schema) - _ALLOWED_SCHEMA_KEYWORDS)
    if unknown:
        raise ValueError(
            f"structured completion conformance profile rejects unsupported schema keywords at {path}: {unknown}"
        )

    type_name = schema.get("type")
    if type_name is not None:
        if not isinstance(type_name, str) or type_name not in _ALLOWED_TYPE_NAMES:
            raise ValueError(
                f"structured completion conformance profile rejects type at {path}: {type_name!r}"
            )

    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, Mapping):
            raise ValueError(f"structured completion properties at {path} must be an object")
        for name, child in properties.items():
            if not isinstance(name, str) or not isinstance(child, Mapping):
                raise ValueError(
                    f"structured completion property schemas at {path} must be named objects"
                )
            _require_profile_schema(child, path=f"{path}.properties[{name!r}]")

    items = schema.get("items")
    if items is not None:
        if not isinstance(items, Mapping):
            raise ValueError(f"structured completion items at {path} must be a schema object")
        _require_profile_schema(items, path=f"{path}.items")

    additional = schema.get("additionalProperties")
    if additional is not None and type(additional) is not bool:
        raise ValueError(
            f"structured completion additionalProperties at {path} must be boolean"
        )


def validate_structured_result_schema_policy(
    completion_contract: Mapping[str, Any],
) -> None:
    policy = structured_result_conformance_policy(completion_contract)
    if policy is None:
        return
    raw_schema = completion_contract.get("resultSchema")
    if not isinstance(raw_schema, Mapping):
        raise ValueError("structured completion resultSchema must be an object")
    _require_profile_schema(raw_schema)
    projected = _json_projection(raw_schema)
    assert isinstance(projected, dict)
    try:
        Draft202012Validator.check_schema(projected)
    except SchemaError as error:
        raise ValueError(
            f"structured completion resultSchema is invalid under Draft 2020-12: {error.message}"
        ) from error


def validate_structured_result_instance(
    completion_contract: Mapping[str, Any],
    result: JsonValue,
) -> None:
    policy = structured_result_conformance_policy(completion_contract)
    if policy is None:
        return
    raw_schema = completion_contract.get("resultSchema")
    if not isinstance(raw_schema, Mapping):
        raise ValueError("structured completion resultSchema must be an object")
    schema = _json_projection(raw_schema)
    assert isinstance(schema, dict)
    validate_json_value(result)
    try:
        Draft202012Validator(schema).validate(result)
    except ValidationError as error:
        location = "$result"
        if error.absolute_path:
            location += "".join(
                f"[{item}]" if isinstance(item, int) else f"[{item!r}]"
                for item in error.absolute_path
            )
        raise ValueError(
            f"structured completion result violates bound schema at {location}: {error.message}"
        ) from error


__all__ = [
    "LOCAL_JSON_SCHEMA_DRAFT_2020_12_PROFILE_V1",
    "structured_result_conformance_policy",
    "validate_structured_result_instance",
    "validate_structured_result_schema_policy",
]
