from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from .core_contracts import HarnessBoundReference
from .independent_result import IndependentCompletionProposal, IndependentHarnessRunReceipt
from .mandate import (
    CompiledHarnessAttempt,
    HarnessExecutionMandate,
    HarnessExecutionProfile,
    HarnessExecutionStrategy,
    HarnessMandateConsumption,
    compile_harness_attempt,
)
from .ordivon.loop import RunBudget


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("Harness Strategy Evidence object keys must be strings")
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    validate_json_value(value)
    return value


def _thaw_json(value: Any) -> JsonValue:
    if isinstance(value, Mapping):
        projected = {str(key): _thaw_json(item) for key, item in value.items()}
        validate_json_value(projected)
        return projected
    if isinstance(value, tuple):
        projected_list = [_thaw_json(item) for item in value]
        validate_json_value(projected_list)
        return projected_list
    validate_json_value(value)
    return value


def _receipt_ref(receipt: IndependentHarnessRunReceipt) -> HarnessBoundReference:
    return HarnessBoundReference(
        ref=f"receipt:{receipt.harness_run_id}",
        kind="independent-harness-run-receipt",
        digest=receipt.digest,
    )


def _usage_int(receipt: IndependentHarnessRunReceipt, field: str) -> int:
    value = receipt.usage.get(field)
    if type(value) is not int or value < 0:
        raise ValueError(
            f"Harness Run Receipt {receipt.harness_run_id} must expose non-negative integer usage.{field}"
        )
    return value


@dataclass(frozen=True, slots=True)
class HarnessStrategyEvidence:
    """Exact caller/domain evidence exposed for Agent Strategy choice.

    Harness proves byte identity and addressability only. Presence in a selection
    context does not make the evidence true, authoritative, ranked, or preferred.
    """

    reference: HarnessBoundReference
    content: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        if not isinstance(self.reference, HarnessBoundReference):
            raise TypeError("Harness Strategy Evidence reference is invalid")
        if not isinstance(self.content, Mapping):
            raise TypeError("Harness Strategy Evidence content must be an object")
        frozen = _freeze_json(self.content)
        projected = _thaw_json(frozen)
        if not isinstance(projected, dict):
            raise TypeError("Harness Strategy Evidence content must be an object")
        if canonical_digest(projected) != self.reference.digest:
            raise ValueError("Harness Strategy Evidence digest differs from content")
        object.__setattr__(self, "content", frozen)

    def to_dict(self) -> dict[str, JsonValue]:
        content = _thaw_json(self.content)
        assert isinstance(content, dict)
        return {
            "reference": self.reference.to_dict(),
            "content": content,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessStrategyEvidence:
        if set(value) != {"reference", "content"}:
            raise ValueError("HarnessStrategyEvidence fields differ")
        reference = value["reference"]
        content = value["content"]
        if not isinstance(reference, dict) or not isinstance(content, dict):
            raise ValueError("HarnessStrategyEvidence values are invalid")
        return cls(
            reference=HarnessBoundReference.from_dict(reference),
            content=content,
        )


@dataclass(frozen=True, slots=True)
class HarnessPriorAttemptEvidence:
    """Exact pre-run authority paired with terminal execution and outcome evidence."""

    compiled_attempt: CompiledHarnessAttempt
    receipt: IndependentHarnessRunReceipt
    completion_proposal: IndependentCompletionProposal | None = None

    def __post_init__(self) -> None:
        contract = self.compiled_attempt.contract
        manifest = self.compiled_attempt.to_dict()["systemManifest"]
        assert isinstance(manifest, dict)
        if canonical_digest(manifest) != contract.system_manifest_ref.digest:
            raise ValueError("Harness prior attempt System Manifest bytes differ from Contract")
        if manifest.get("mandateDigest") != self.compiled_attempt.mandate_digest:
            raise ValueError("Harness prior attempt manifest Mandate digest differs")
        if manifest.get("profileDigest") != self.compiled_attempt.profile_digest:
            raise ValueError("Harness prior attempt manifest profile digest differs")
        if manifest.get("strategyDigest") != self.compiled_attempt.strategy_digest:
            raise ValueError("Harness prior attempt manifest Strategy digest differs")
        if self.receipt.harness_run_id != contract.harness_run_id:
            raise ValueError("Harness prior receipt Run identity differs from compiled attempt")
        if self.receipt.caller_id != contract.caller_id:
            raise ValueError("Harness prior receipt caller differs from compiled attempt")
        if self.receipt.caller_run_ref != contract.caller_run_ref:
            raise ValueError("Harness prior receipt caller Run reference differs")
        if self.receipt.contract_digest != contract.digest:
            raise ValueError("Harness prior receipt Contract digest differs")
        if self.receipt.system_manifest_digest != contract.system_manifest_ref.digest:
            raise ValueError("Harness prior receipt System Manifest digest differs")
        proposal = self.completion_proposal
        if proposal is not None:
            if proposal.harness_run_id != self.receipt.harness_run_id:
                raise ValueError("Harness prior Completion Proposal Run identity differs")
            if proposal.caller_id != self.receipt.caller_id:
                raise ValueError("Harness prior Completion Proposal caller differs")
            if proposal.caller_run_ref != self.receipt.caller_run_ref:
                raise ValueError("Harness prior Completion Proposal caller Run reference differs")
            if proposal.contract_digest != self.receipt.contract_digest:
                raise ValueError("Harness prior Completion Proposal Contract digest differs")
            if proposal.run_receipt_digest != self.receipt.digest:
                raise ValueError("Harness prior Completion Proposal Receipt digest differs")
            if proposal.trace_digest != self.receipt.trace_digest:
                raise ValueError("Harness prior Completion Proposal Trace digest differs")
            if self.receipt.stop_reason != "completed":
                raise ValueError("non-completed Harness prior attempt cannot carry a Completion Proposal")

    @property
    def attempt_index(self) -> int:
        value = self.compiled_attempt.system_manifest.get("attemptIndex")
        if type(value) is not int or value < 1:
            raise ValueError("Harness prior attempt manifest attemptIndex is invalid")
        return value

    @property
    def receipt_ref(self) -> HarnessBoundReference:
        return _receipt_ref(self.receipt)

    @property
    def completion_proposal_ref(self) -> HarnessBoundReference | None:
        proposal = self.completion_proposal
        if proposal is None:
            return None
        return HarnessBoundReference(
            ref=f"completion-proposal:{self.receipt.harness_run_id}",
            kind="independent-completion-proposal",
            digest=proposal.digest,
        )

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "compiledAttempt": self.compiled_attempt.to_dict(),
            "receipt": self.receipt.to_dict(),
        }
        if self.completion_proposal is not None:
            value["completionProposal"] = self.completion_proposal.to_dict()
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessPriorAttemptEvidence:
        fields = set(value)
        if fields not in (
            {"compiledAttempt", "receipt"},
            {"compiledAttempt", "receipt", "completionProposal"},
        ):
            raise ValueError("HarnessPriorAttemptEvidence fields differ")
        compiled = value["compiledAttempt"]
        receipt = value["receipt"]
        proposal = value.get("completionProposal")
        if not isinstance(compiled, dict) or not isinstance(receipt, dict):
            raise ValueError("HarnessPriorAttemptEvidence values are invalid")
        if proposal is not None and not isinstance(proposal, dict):
            raise ValueError("HarnessPriorAttemptEvidence Completion Proposal is invalid")
        return cls(
            compiled_attempt=CompiledHarnessAttempt.from_dict(compiled),
            receipt=IndependentHarnessRunReceipt.from_dict(receipt),
            completion_proposal=(
                None if proposal is None else IndependentCompletionProposal.from_dict(proposal)
            ),
        )


def derive_harness_mandate_consumption(
    mandate: HarnessExecutionMandate,
    prior_attempts: tuple[HarnessPriorAttemptEvidence, ...],
) -> HarnessMandateConsumption:
    """Derive aggregate Mandate consumption from exact terminal attempt evidence.

    Each receipt must be paired with the immutable compiled attempt that preceded
    it. That pair proves the exact Mandate digest, Contract, System Manifest and
    attempt index instead of trusting a same-named caller reference.
    """

    run_ids: set[str] = set()
    receipt_digests: set[str] = set()
    refs: list[HarnessBoundReference] = []
    consumed_tokens = 0
    consumed_wall_time = 0
    for expected_index, evidence in enumerate(prior_attempts, start=1):
        attempt = evidence.compiled_attempt
        receipt = evidence.receipt
        manifest = attempt.system_manifest
        if attempt.mandate_digest != mandate.digest:
            raise ValueError("Harness prior attempt is bound to a different Mandate digest")
        if manifest.get("mandateId") != mandate.mandate_id:
            raise ValueError("Harness prior attempt manifest Mandate identity differs")
        if attempt.contract.caller_id != mandate.caller_id:
            raise ValueError("Harness prior attempt caller differs from Mandate")
        if attempt.contract.caller_run_ref != mandate.mandate_id:
            raise ValueError("Harness prior attempt caller Run reference differs from Mandate")
        if evidence.attempt_index != expected_index:
            raise ValueError("Harness prior attempts are not a contiguous ordered lineage")
        if receipt.harness_run_id in run_ids:
            raise ValueError("Harness Mandate evidence contains a duplicate Run identity")
        if receipt.digest in receipt_digests:
            raise ValueError("Harness Mandate evidence contains duplicate receipt bytes")
        run_ids.add(receipt.harness_run_id)
        receipt_digests.add(receipt.digest)
        consumed_tokens += _usage_int(receipt, "totalTokens")
        consumed_wall_time += _usage_int(receipt, "wallTimeMs")
        refs.append(evidence.receipt_ref)
    return HarnessMandateConsumption(
        mandate_digest=mandate.digest,
        completed_attempts=len(prior_attempts),
        consumed_total_tokens=consumed_tokens,
        consumed_wall_time_ms=consumed_wall_time,
        receipt_refs=tuple(refs),
    )


@dataclass(frozen=True, slots=True)
class HarnessStrategySelectionContext:
    """Exact evidence and capability surface from which an Agent selects a Strategy.

    Harness constructs and validates this surface mechanically. It does not rank
    profiles, summarize evidence, choose Context, or select the next Strategy.
    """

    mandate: HarnessExecutionMandate
    profiles: tuple[HarnessExecutionProfile, ...]
    prior_attempts: tuple[HarnessPriorAttemptEvidence, ...]
    consumption: HarnessMandateConsumption
    strategy_evidence: tuple[HarnessStrategyEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not self.profiles:
            raise ValueError("Harness Strategy selection requires available profiles")
        profile_ids = [profile.profile_id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("Harness Strategy selection profile identities must be unique")
        disallowed = sorted(
            profile_id
            for profile_id in profile_ids
            if profile_id not in self.mandate.allowed_profile_ids
        )
        if disallowed:
            raise ValueError(
                "Harness Strategy selection contains profiles outside the Mandate: "
                + ", ".join(disallowed)
            )
        if any(not isinstance(item, HarnessStrategyEvidence) for item in self.strategy_evidence):
            raise TypeError("Harness Strategy selection evidence is invalid")
        strategy_refs = [item.reference.ref for item in self.strategy_evidence]
        if len(strategy_refs) != len(set(strategy_refs)):
            raise ValueError("Harness Strategy selection evidence references must be unique")
        occupied_refs = {evidence.receipt_ref.ref for evidence in self.prior_attempts}
        occupied_refs.update(
            proposal_ref.ref
            for evidence in self.prior_attempts
            if (proposal_ref := evidence.completion_proposal_ref) is not None
        )
        if occupied_refs.intersection(strategy_refs):
            raise ValueError("Harness Strategy selection evidence reference conflicts with prior attempt evidence")
        derived = derive_harness_mandate_consumption(self.mandate, self.prior_attempts)
        if derived != self.consumption:
            raise ValueError("Harness Strategy selection consumption differs from attempt evidence")

    @property
    def receipts(self) -> tuple[IndependentHarnessRunReceipt, ...]:
        return tuple(evidence.receipt for evidence in self.prior_attempts)

    @property
    def attempt_index(self) -> int:
        return self.consumption.completed_attempts + 1

    @property
    def remaining_total_tokens(self) -> int:
        return max(
            0,
            self.mandate.max_total_tokens - self.consumption.consumed_total_tokens,
        )

    @property
    def remaining_wall_time_ms(self) -> int:
        return max(
            0,
            self.mandate.max_wall_time_ms - self.consumption.consumed_wall_time_ms,
        )

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-strategy-selection-context",
            "mandate": self.mandate.to_dict(),
            "attemptIndex": self.attempt_index,
            "availableProfiles": [profile.to_dict() for profile in self.profiles],
            "priorAttempts": [evidence.to_dict() for evidence in self.prior_attempts],
            "consumption": self.consumption.to_dict(),
            "remainingEconomicEnvelope": {
                "maxTotalTokens": self.remaining_total_tokens,
                "maxWallTimeMs": self.remaining_wall_time_ms,
            },
        }
        if self.strategy_evidence:
            value["strategyEvidence"] = [evidence.to_dict() for evidence in self.strategy_evidence]
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessStrategySelectionContext:
        base_fields = {
            "schemaVersion",
            "kind",
            "mandate",
            "attemptIndex",
            "availableProfiles",
            "priorAttempts",
            "consumption",
            "remainingEconomicEnvelope",
        }
        if set(value) not in (base_fields, base_fields | {"strategyEvidence"}):
            raise ValueError("HarnessStrategySelectionContext fields differ")
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-strategy-selection-context"
        ):
            raise ValueError("HarnessStrategySelectionContext version or kind is invalid")
        raw_mandate = value["mandate"]
        raw_profiles = value["availableProfiles"]
        raw_attempts = value["priorAttempts"]
        raw_strategy_evidence = value.get("strategyEvidence", [])
        raw_consumption = value["consumption"]
        if not isinstance(raw_mandate, dict):
            raise ValueError("HarnessStrategySelectionContext mandate is invalid")
        if not isinstance(raw_profiles, list) or any(
            not isinstance(item, dict) for item in raw_profiles
        ):
            raise ValueError("HarnessStrategySelectionContext profiles are invalid")
        if not isinstance(raw_attempts, list) or any(
            not isinstance(item, dict) for item in raw_attempts
        ):
            raise ValueError("HarnessStrategySelectionContext prior attempts are invalid")
        if not isinstance(raw_strategy_evidence, list) or any(
            not isinstance(item, dict) for item in raw_strategy_evidence
        ):
            raise ValueError("HarnessStrategySelectionContext Strategy evidence is invalid")
        if not isinstance(raw_consumption, dict):
            raise ValueError("HarnessStrategySelectionContext consumption is invalid")
        context = cls(
            mandate=HarnessExecutionMandate.from_dict(raw_mandate),
            profiles=tuple(HarnessExecutionProfile.from_dict(item) for item in raw_profiles),
            prior_attempts=tuple(HarnessPriorAttemptEvidence.from_dict(item) for item in raw_attempts),
            consumption=HarnessMandateConsumption.from_dict(raw_consumption),
            strategy_evidence=tuple(
                HarnessStrategyEvidence.from_dict(item) for item in raw_strategy_evidence
            ),
        )
        envelope = value["remainingEconomicEnvelope"]
        if (
            type(value["attemptIndex"]) is not int
            or value["attemptIndex"] != context.attempt_index
            or not isinstance(envelope, dict)
            or envelope
            != {
                "maxTotalTokens": context.remaining_total_tokens,
                "maxWallTimeMs": context.remaining_wall_time_ms,
            }
        ):
            raise ValueError("HarnessStrategySelectionContext derived projection differs")
        return context


@dataclass(frozen=True, slots=True)
class HarnessAgentStrategySelection:
    """One Agent-authored Strategy bound to the exact selection context it saw."""

    selection_context_digest: str
    strategy: HarnessExecutionStrategy

    def __post_init__(self) -> None:
        if (
            not self.selection_context_digest.startswith("sha256:")
            or len(self.selection_context_digest) != 71
            or any(character not in "0123456789abcdef" for character in self.selection_context_digest[7:])
        ):
            raise ValueError("Harness Strategy selection context digest is invalid")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-agent-strategy-selection",
            "selectionContextDigest": self.selection_context_digest,
            "strategy": self.strategy.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessAgentStrategySelection:
        expected = {"schemaVersion", "kind", "selectionContextDigest", "strategy"}
        if set(value) != expected:
            raise ValueError("HarnessAgentStrategySelection fields differ")
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-agent-strategy-selection"
            or not isinstance(value["selectionContextDigest"], str)
            or not isinstance(value["strategy"], dict)
        ):
            raise ValueError("HarnessAgentStrategySelection version or fields are invalid")
        return cls(
            selection_context_digest=value["selectionContextDigest"],
            strategy=HarnessExecutionStrategy.from_dict(value["strategy"]),
        )


def build_harness_strategy_selection_context(
    mandate: HarnessExecutionMandate,
    profiles: tuple[HarnessExecutionProfile, ...],
    prior_attempts: tuple[HarnessPriorAttemptEvidence, ...] = (),
    strategy_evidence: tuple[HarnessStrategyEvidence, ...] = (),
) -> HarnessStrategySelectionContext:
    return HarnessStrategySelectionContext(
        mandate=mandate,
        profiles=profiles,
        prior_attempts=prior_attempts,
        consumption=derive_harness_mandate_consumption(mandate, prior_attempts),
        strategy_evidence=strategy_evidence,
    )


def admit_harness_agent_strategy(
    context: HarnessStrategySelectionContext,
    selection: HarnessAgentStrategySelection,
) -> HarnessExecutionProfile:
    """Admit an Agent choice without choosing a profile or budget on its behalf."""

    if selection.selection_context_digest != context.digest:
        raise ValueError("Harness Agent Strategy was selected from a stale context")
    strategy = selection.strategy
    if strategy.mandate_digest != context.mandate.digest:
        raise ValueError("Harness Agent Strategy is bound to another Mandate")
    if strategy.attempt_index != context.attempt_index:
        raise ValueError("Harness Agent Strategy attempt index differs from evidence")
    matches = tuple(
        profile for profile in context.profiles if profile.profile_id == strategy.profile_id
    )
    if len(matches) != 1:
        raise ValueError("Harness Agent Strategy selected an unavailable profile")
    budget_value = dict(strategy.budget)
    budget = RunBudget.from_contract_dict(budget_value)
    if budget.max_total_tokens > context.remaining_total_tokens:
        raise ValueError("Harness Agent Strategy exceeds remaining Mandate token authority")
    if budget.max_wall_time_ms > context.remaining_wall_time_ms:
        raise ValueError("Harness Agent Strategy exceeds remaining Mandate wall-time authority")
    available_refs = {item.ref: item for item in context.consumption.receipt_refs}
    for evidence in context.prior_attempts:
        proposal_ref = evidence.completion_proposal_ref
        if proposal_ref is not None:
            available_refs[proposal_ref.ref] = proposal_ref
    for evidence in context.strategy_evidence:
        available_refs[evidence.reference.ref] = evidence.reference
    for adopted in strategy.adopted_context_refs:
        available = available_refs.get(adopted.ref)
        if available is None or available != adopted:
            raise ValueError(
                "Harness Agent Strategy adopted Context is not an exact prior receipt, Completion Proposal, or Strategy Evidence"
            )
    return matches[0]


def compile_harness_selected_attempt(
    context: HarnessStrategySelectionContext,
    selection: HarnessAgentStrategySelection,
    *,
    harness_run_id: str,
    harness_implementation_id: str,
    created_at_ms: int,
) -> CompiledHarnessAttempt:
    """Resolve the Agent-selected profile mechanically and freeze one Run attempt."""

    profile = admit_harness_agent_strategy(context, selection)
    return compile_harness_attempt(
        context.mandate,
        profile,
        selection.strategy,
        consumption=context.consumption,
        harness_run_id=harness_run_id,
        harness_implementation_id=harness_implementation_id,
        created_at_ms=created_at_ms,
    )


__all__ = [
    "HarnessAgentStrategySelection",
    "HarnessPriorAttemptEvidence",
    "HarnessStrategyEvidence",
    "HarnessStrategySelectionContext",
    "admit_harness_agent_strategy",
    "build_harness_strategy_selection_context",
    "compile_harness_selected_attempt",
    "derive_harness_mandate_consumption",
]
