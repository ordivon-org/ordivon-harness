from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from .core_contracts import HarnessBoundReference, HarnessPrivacyPolicy, HarnessRunContract
from .ordivon.loop import RunBudget


def _text(value: str, label: str, *, max_bytes: int = 4_096) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _digest(value: str, label: str) -> str:
    _text(value, label, max_bytes=80)
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{label} must be a sha256 digest")
    return value


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("authority object keys must be strings")
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    validate_json_value(value)
    return value


def _thaw_json(value: Any) -> JsonValue:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("authority object keys must be strings")
        projected = {key: _thaw_json(item) for key, item in value.items()}
        validate_json_value(projected)
        return projected
    if isinstance(value, tuple):
        projected_list = [_thaw_json(item) for item in value]
        validate_json_value(projected_list)
        return projected_list
    validate_json_value(value)
    return value


def _json_object(value: Mapping[str, Any], label: str, *, non_empty: bool = False) -> dict[str, JsonValue]:
    projected = _thaw_json(value)
    if not isinstance(projected, dict):
        raise TypeError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in projected):
        raise TypeError(f"{label} object keys must be strings")
    if non_empty and not projected:
        raise ValueError(f"{label} must not be empty")
    return projected


def _unique_text(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if not values:
        raise ValueError(f"{label} must not be empty")
    for value in values:
        _text(value, label)
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must not contain duplicates")
    return values


@dataclass(frozen=True, slots=True)
class HarnessExecutionMandate:
    """Caller delegation above one or more immutable Harness Run attempts.

    A Mandate fixes what may be pursued and the aggregate capability/resource
    envelope. It deliberately does not prescribe model-call or Tool-call counts.
    """

    mandate_id: str
    caller_id: str
    caller_ref: str
    objective_ref: HarnessBoundReference
    context_refs: tuple[HarnessBoundReference, ...]
    allowed_profile_ids: tuple[str, ...]
    max_total_tokens: int
    max_wall_time_ms: int
    completion_contract: Mapping[str, JsonValue]
    created_at_ms: int
    privacy: HarnessPrivacyPolicy | None = None

    def __post_init__(self) -> None:
        _text(self.mandate_id, "Harness Mandate identity")
        _text(self.caller_id, "Harness Mandate caller identity")
        _text(self.caller_ref, "Harness Mandate caller reference")
        if not isinstance(self.objective_ref, HarnessBoundReference):
            raise TypeError("Harness Mandate objective_ref is invalid")
        if not self.context_refs or any(
            not isinstance(item, HarnessBoundReference) for item in self.context_refs
        ):
            raise ValueError("Harness Mandate requires bound Context references")
        if len({item.ref for item in self.context_refs}) != len(self.context_refs):
            raise ValueError("Harness Mandate Context references must be unique")
        _unique_text(self.allowed_profile_ids, "Harness Mandate execution profile")
        if type(self.max_total_tokens) is not int or self.max_total_tokens < 1:
            raise ValueError("Harness Mandate max_total_tokens must be positive")
        if type(self.max_wall_time_ms) is not int or self.max_wall_time_ms < 1:
            raise ValueError("Harness Mandate max_wall_time_ms must be positive")
        if type(self.created_at_ms) is not int or self.created_at_ms < 0:
            raise ValueError("Harness Mandate creation time must be non-negative")
        if self.privacy is not None and not isinstance(self.privacy, HarnessPrivacyPolicy):
            raise TypeError("Harness Mandate privacy policy is invalid")
        completion = _json_object(
            self.completion_contract,
            "Harness Mandate completion contract",
            non_empty=True,
        )
        object.__setattr__(self, "completion_contract", _freeze_json(completion))

    @property
    def effective_privacy(self) -> HarnessPrivacyPolicy:
        return self.privacy or HarnessPrivacyPolicy()

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        completion = _thaw_json(self.completion_contract)
        assert isinstance(completion, dict)
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-execution-mandate",
            "mandateId": self.mandate_id,
            "callerId": self.caller_id,
            "callerRef": self.caller_ref,
            "objectiveRef": self.objective_ref.to_dict(),
            "contextRefs": [item.to_dict() for item in self.context_refs],
            "allowedProfileIds": list(self.allowed_profile_ids),
            "economicEnvelope": {
                "maxTotalTokens": self.max_total_tokens,
                "maxWallTimeMs": self.max_wall_time_ms,
            },
            "completionContract": completion,
            "createdAtMs": self.created_at_ms,
        }
        if self.privacy is not None:
            value["privacy"] = self.privacy.to_dict()
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessExecutionMandate:
        base_fields = {
            "schemaVersion",
            "kind",
            "mandateId",
            "callerId",
            "callerRef",
            "objectiveRef",
            "contextRefs",
            "allowedProfileIds",
            "economicEnvelope",
            "completionContract",
            "createdAtMs",
        }
        if set(value) not in (base_fields, base_fields | {"privacy"}):
            raise ValueError("HarnessExecutionMandate fields differ")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.harness-execution-mandate":
            raise ValueError("HarnessExecutionMandate version or kind is invalid")
        context = value["contextRefs"]
        profiles = value["allowedProfileIds"]
        economic = value["economicEnvelope"]
        if not isinstance(context, list) or any(not isinstance(item, dict) for item in context):
            raise ValueError("HarnessExecutionMandate contextRefs are invalid")
        if not isinstance(profiles, list) or any(not isinstance(item, str) for item in profiles):
            raise ValueError("HarnessExecutionMandate allowedProfileIds are invalid")
        if not isinstance(economic, dict) or set(economic) != {"maxTotalTokens", "maxWallTimeMs"}:
            raise ValueError("HarnessExecutionMandate economicEnvelope is invalid")
        objective = value["objectiveRef"]
        completion = value["completionContract"]
        privacy = value.get("privacy")
        if not isinstance(objective, dict) or not isinstance(completion, dict):
            raise ValueError("HarnessExecutionMandate bound data is invalid")
        if privacy is not None and not isinstance(privacy, dict):
            raise ValueError("HarnessExecutionMandate privacy is invalid")
        return cls(
            mandate_id=value["mandateId"],
            caller_id=value["callerId"],
            caller_ref=value["callerRef"],
            objective_ref=HarnessBoundReference.from_dict(objective),
            context_refs=tuple(HarnessBoundReference.from_dict(item) for item in context),
            allowed_profile_ids=tuple(profiles),
            max_total_tokens=economic["maxTotalTokens"],
            max_wall_time_ms=economic["maxWallTimeMs"],
            completion_contract=completion,
            created_at_ms=value["createdAtMs"],
            privacy=(None if privacy is None else HarnessPrivacyPolicy.from_dict(privacy)),
        )


@dataclass(frozen=True, slots=True)
class HarnessMandateConsumption:
    """Caller-supplied aggregate consumption reconstructed from prior Run receipts."""

    mandate_digest: str
    completed_attempts: int
    consumed_total_tokens: int
    consumed_wall_time_ms: int
    receipt_refs: tuple[HarnessBoundReference, ...] = ()

    def __post_init__(self) -> None:
        _digest(self.mandate_digest, "Harness Mandate consumption digest")
        for value, label in (
            (self.completed_attempts, "completed attempts"),
            (self.consumed_total_tokens, "consumed total tokens"),
            (self.consumed_wall_time_ms, "consumed wall time"),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"Harness Mandate {label} must be non-negative")
        if any(not isinstance(item, HarnessBoundReference) for item in self.receipt_refs):
            raise TypeError("Harness Mandate receipt reference is invalid")
        if len({item.ref for item in self.receipt_refs}) != len(self.receipt_refs):
            raise ValueError("Harness Mandate receipt references must be unique")

    @classmethod
    def empty(cls, mandate: HarnessExecutionMandate) -> HarnessMandateConsumption:
        return cls(
            mandate_digest=mandate.digest,
            completed_attempts=0,
            consumed_total_tokens=0,
            consumed_wall_time_ms=0,
        )

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-mandate-consumption",
            "mandateDigest": self.mandate_digest,
            "completedAttempts": self.completed_attempts,
            "consumedTotalTokens": self.consumed_total_tokens,
            "consumedWallTimeMs": self.consumed_wall_time_ms,
            "receiptRefs": [item.to_dict() for item in self.receipt_refs],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessMandateConsumption:
        expected = {
            "schemaVersion", "kind", "mandateDigest", "completedAttempts",
            "consumedTotalTokens", "consumedWallTimeMs", "receiptRefs",
        }
        if set(value) != expected:
            raise ValueError("HarnessMandateConsumption fields differ")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.harness-mandate-consumption":
            raise ValueError("HarnessMandateConsumption version or kind is invalid")
        refs = value["receiptRefs"]
        if not isinstance(refs, list) or any(not isinstance(item, dict) for item in refs):
            raise ValueError("HarnessMandateConsumption receiptRefs are invalid")
        return cls(
            mandate_digest=value["mandateDigest"],
            completed_attempts=value["completedAttempts"],
            consumed_total_tokens=value["consumedTotalTokens"],
            consumed_wall_time_ms=value["consumedWallTimeMs"],
            receipt_refs=tuple(HarnessBoundReference.from_dict(item) for item in refs),
        )


@dataclass(frozen=True, slots=True)
class HarnessExecutionProfile:
    """One concrete Provider/Tool capability profile selectable under a Mandate."""

    profile_id: str
    provider_id: str
    adapter_id: str
    requested_model_id: str
    tool_catalog_digest: str
    tool_grant_digest: str
    metadata: Mapping[str, JsonValue] = MappingProxyType({})

    def __post_init__(self) -> None:
        for value, label in (
            (self.profile_id, "Harness execution profile identity"),
            (self.provider_id, "Harness Provider identity"),
            (self.adapter_id, "Harness Adapter identity"),
            (self.requested_model_id, "Harness requested model identity"),
        ):
            _text(value, label)
        _digest(self.tool_catalog_digest, "Harness Tool catalog digest")
        _digest(self.tool_grant_digest, "Harness Tool Grant digest")
        metadata = _json_object(self.metadata, "Harness execution profile metadata")
        object.__setattr__(self, "metadata", _freeze_json(metadata))

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        metadata = _thaw_json(self.metadata)
        assert isinstance(metadata, dict)
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-execution-profile",
            "profileId": self.profile_id,
            "providerId": self.provider_id,
            "adapterId": self.adapter_id,
            "requestedModelId": self.requested_model_id,
            "toolCatalogDigest": self.tool_catalog_digest,
            "toolGrantDigest": self.tool_grant_digest,
            "metadata": metadata,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessExecutionProfile:
        expected = {
            "schemaVersion", "kind", "profileId", "providerId", "adapterId",
            "requestedModelId", "toolCatalogDigest", "toolGrantDigest", "metadata",
        }
        if set(value) != expected:
            raise ValueError("HarnessExecutionProfile fields differ")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.harness-execution-profile":
            raise ValueError("HarnessExecutionProfile version or kind is invalid")
        metadata = value["metadata"]
        if not isinstance(metadata, dict):
            raise ValueError("HarnessExecutionProfile metadata is invalid")
        return cls(
            profile_id=value["profileId"],
            provider_id=value["providerId"],
            adapter_id=value["adapterId"],
            requested_model_id=value["requestedModelId"],
            tool_catalog_digest=value["toolCatalogDigest"],
            tool_grant_digest=value["toolGrantDigest"],
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class HarnessExecutionStrategy:
    """One chosen attempt strategy inside a Mandate envelope."""

    mandate_digest: str
    attempt_index: int
    profile_id: str
    budget: Mapping[str, JsonValue]
    provider_options: Mapping[str, JsonValue]
    adopted_context_refs: tuple[HarnessBoundReference, ...] = ()
    rationale: str = "strategy selected"

    def __post_init__(self) -> None:
        _digest(self.mandate_digest, "Harness Mandate digest")
        if type(self.attempt_index) is not int or self.attempt_index < 1:
            raise ValueError("Harness strategy attempt_index must be positive")
        _text(self.profile_id, "Harness strategy profile identity")
        _text(self.rationale, "Harness strategy rationale", max_bytes=16_384)
        budget = _json_object(self.budget, "Harness strategy budget", non_empty=True)
        parsed = RunBudget.from_contract_dict(budget)
        if set(budget) != set(parsed.to_contract_dict()):
            raise ValueError("Harness strategy budget must bind every current RunBudget field")
        provider_options = _json_object(
            self.provider_options,
            "Harness strategy Provider options",
        )
        if any(not isinstance(item, HarnessBoundReference) for item in self.adopted_context_refs):
            raise TypeError("Harness strategy adopted Context reference is invalid")
        if len({item.ref for item in self.adopted_context_refs}) != len(
            self.adopted_context_refs
        ):
            raise ValueError("Harness strategy adopted Context references must be unique")
        object.__setattr__(self, "budget", _freeze_json(budget))
        object.__setattr__(self, "provider_options", _freeze_json(provider_options))

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        budget = _thaw_json(self.budget)
        provider_options = _thaw_json(self.provider_options)
        assert isinstance(budget, dict) and isinstance(provider_options, dict)
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-execution-strategy",
            "mandateDigest": self.mandate_digest,
            "attemptIndex": self.attempt_index,
            "profileId": self.profile_id,
            "budget": budget,
            "providerOptions": provider_options,
            "adoptedContextRefs": [item.to_dict() for item in self.adopted_context_refs],
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessExecutionStrategy:
        expected = {
            "schemaVersion", "kind", "mandateDigest", "attemptIndex", "profileId",
            "budget", "providerOptions", "adoptedContextRefs", "rationale",
        }
        if set(value) != expected:
            raise ValueError("HarnessExecutionStrategy fields differ")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.harness-execution-strategy":
            raise ValueError("HarnessExecutionStrategy version or kind is invalid")
        budget = value["budget"]
        options = value["providerOptions"]
        refs = value["adoptedContextRefs"]
        if not isinstance(budget, dict) or not isinstance(options, dict):
            raise ValueError("HarnessExecutionStrategy bound objects are invalid")
        if not isinstance(refs, list) or any(not isinstance(item, dict) for item in refs):
            raise ValueError("HarnessExecutionStrategy adoptedContextRefs are invalid")
        return cls(
            mandate_digest=value["mandateDigest"],
            attempt_index=value["attemptIndex"],
            profile_id=value["profileId"],
            budget=budget,
            provider_options=options,
            adopted_context_refs=tuple(HarnessBoundReference.from_dict(item) for item in refs),
            rationale=value["rationale"],
        )


@dataclass(frozen=True, slots=True)
class CompiledHarnessAttempt:
    mandate_digest: str
    profile_digest: str
    strategy_digest: str
    system_manifest: Mapping[str, JsonValue]
    contract: HarnessRunContract

    def __post_init__(self) -> None:
        _digest(self.mandate_digest, "compiled Harness Mandate digest")
        _digest(self.profile_digest, "compiled Harness profile digest")
        _digest(self.strategy_digest, "compiled Harness strategy digest")
        manifest = _json_object(
            self.system_manifest,
            "compiled Harness system manifest",
            non_empty=True,
        )
        object.__setattr__(self, "system_manifest", _freeze_json(manifest))

    def to_dict(self) -> dict[str, JsonValue]:
        manifest = _thaw_json(self.system_manifest)
        assert isinstance(manifest, dict)
        return {
            "schemaVersion": 1,
            "kind": "ordivon.compiled-harness-attempt",
            "mandateDigest": self.mandate_digest,
            "profileDigest": self.profile_digest,
            "strategyDigest": self.strategy_digest,
            "systemManifest": manifest,
            "contract": self.contract.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CompiledHarnessAttempt:
        expected = {
            "schemaVersion",
            "kind",
            "mandateDigest",
            "profileDigest",
            "strategyDigest",
            "systemManifest",
            "contract",
        }
        if set(value) != expected:
            raise ValueError("CompiledHarnessAttempt fields differ")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.compiled-harness-attempt":
            raise ValueError("CompiledHarnessAttempt version or kind is invalid")
        manifest = value["systemManifest"]
        contract = value["contract"]
        if not isinstance(manifest, dict) or not isinstance(contract, dict):
            raise ValueError("CompiledHarnessAttempt manifest or contract is invalid")
        return cls(
            mandate_digest=value["mandateDigest"],
            profile_digest=value["profileDigest"],
            strategy_digest=value["strategyDigest"],
            system_manifest=manifest,
            contract=HarnessRunContract.from_dict(contract),
        )


def compile_harness_attempt(
    mandate: HarnessExecutionMandate,
    profile: HarnessExecutionProfile,
    strategy: HarnessExecutionStrategy,
    *,
    consumption: HarnessMandateConsumption | None = None,
    harness_run_id: str,
    harness_implementation_id: str,
    created_at_ms: int,
) -> CompiledHarnessAttempt:
    """Compile caller delegation + Agent strategy into one immutable Run attempt."""

    if strategy.mandate_digest != mandate.digest:
        raise ValueError("Harness strategy is bound to a different Mandate")
    if consumption is None:
        if strategy.attempt_index != 1:
            raise ValueError("later Harness Mandate attempts require explicit consumption")
        consumption = HarnessMandateConsumption.empty(mandate)
    if consumption.mandate_digest != mandate.digest:
        raise ValueError("Harness Mandate consumption is bound to a different Mandate")
    if consumption.completed_attempts != strategy.attempt_index - 1:
        raise ValueError("Harness Mandate consumption attempt count differs from Strategy")
    if strategy.profile_id != profile.profile_id:
        raise ValueError("Harness strategy and execution profile differ")
    if profile.profile_id not in mandate.allowed_profile_ids:
        raise ValueError("Harness execution profile is outside the Mandate capability envelope")
    budget_value = _thaw_json(strategy.budget)
    assert isinstance(budget_value, dict)
    budget = RunBudget.from_contract_dict(budget_value)
    remaining_tokens = mandate.max_total_tokens - consumption.consumed_total_tokens
    remaining_wall_time = mandate.max_wall_time_ms - consumption.consumed_wall_time_ms
    if remaining_tokens < 1:
        raise ValueError("Harness Mandate total-token envelope is exhausted")
    if remaining_wall_time < 1:
        raise ValueError("Harness Mandate wall-time envelope is exhausted")
    if budget.max_total_tokens > remaining_tokens:
        raise ValueError("Harness strategy exceeds remaining Mandate total-token envelope")
    if budget.max_wall_time_ms > remaining_wall_time:
        raise ValueError("Harness strategy exceeds remaining Mandate wall-time envelope")

    combined_context = mandate.context_refs + strategy.adopted_context_refs
    reference_ids = [item.ref for item in combined_context]
    if len(set(reference_ids)) != len(reference_ids):
        raise ValueError("compiled Harness attempt Context references conflict")

    manifest: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-execution-attempt-manifest",
        "mandateId": mandate.mandate_id,
        "mandateDigest": mandate.digest,
        "mandateCallerRef": mandate.caller_ref,
        "attemptIndex": strategy.attempt_index,
        "profileId": profile.profile_id,
        "profileDigest": profile.digest,
        "strategyDigest": strategy.digest,
        "mandateConsumptionDigest": consumption.digest,
        "remainingEconomicEnvelope": {
            "maxTotalTokens": remaining_tokens,
            "maxWallTimeMs": remaining_wall_time,
        },
        "priorReceiptDigests": [item.digest for item in consumption.receipt_refs],
        "providerOptions": _thaw_json(strategy.provider_options),
        "adoptedContextDigests": [
            item.digest for item in strategy.adopted_context_refs
        ],
    }
    system_manifest_ref = HarnessBoundReference(
        ref=f"system-manifest:{harness_run_id}",
        kind="harness-execution-attempt-manifest",
        digest=canonical_digest(manifest),
    )
    completion = _thaw_json(mandate.completion_contract)
    assert isinstance(completion, dict)
    contract = HarnessRunContract(
        harness_run_id=harness_run_id,
        harness_implementation_id=harness_implementation_id,
        caller_id=mandate.caller_id,
        caller_run_ref=mandate.mandate_id,
        objective_ref=mandate.objective_ref,
        context_refs=combined_context,
        provider_id=profile.provider_id,
        adapter_id=profile.adapter_id,
        requested_model_id=profile.requested_model_id,
        tool_catalog_digest=profile.tool_catalog_digest,
        tool_grant_digest=profile.tool_grant_digest,
        budget=budget.to_contract_dict(),
        completion_contract=completion,
        system_manifest_ref=system_manifest_ref,
        created_at_ms=created_at_ms,
        privacy=mandate.effective_privacy,
    )
    return CompiledHarnessAttempt(
        mandate_digest=mandate.digest,
        profile_digest=profile.digest,
        strategy_digest=strategy.digest,
        system_manifest=manifest,
        contract=contract,
    )


__all__ = [
    "CompiledHarnessAttempt",
    "HarnessExecutionMandate",
    "HarnessMandateConsumption",
    "HarnessExecutionProfile",
    "HarnessExecutionStrategy",
    "compile_harness_attempt",
]
