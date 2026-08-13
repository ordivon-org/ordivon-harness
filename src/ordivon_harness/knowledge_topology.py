"""Cross-Run reusable cognition without a Harness-owned Memory or Skill store.

The structures in this module are admission helpers and read-only topology
projections.  They let an application/Host/domain resolve one exact externally
owned knowledge/procedure source into the existing Harness cognition seed path.
They do not discover, rank, evaluate, promote, persist or automatically inject
knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from .standalone import HarnessCognitionSeed, HarnessCognitionSeedSource
from .working_view import HarnessWorkingViewSource

_REUSABLE_ROLES = {"knowledge", "procedure"}


def _text(value: Any, label: str, *, max_bytes: int = 500) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")
    return value


@dataclass(frozen=True, slots=True)
class HarnessReusableCognitionReference:
    """One exact external knowledge/procedure source identity.

    `logical_ref` and `logical_generation` are owner-qualified opaque identities
    chosen by the external source owner. `source_digest` binds the exact
    `HarnessWorkingViewSource` value that may be admitted into a Run.

    `role` is descriptive topology metadata only. Marking a source as a procedure
    does not grant Tool authority, prove the procedure correct, or make it current
    cognition.
    """

    role: str
    logical_ref: str
    logical_generation: str
    source_digest: str

    def __post_init__(self) -> None:
        if self.role not in _REUSABLE_ROLES:
            raise ValueError("Reusable cognition role must be knowledge or procedure")
        _text(self.logical_ref, "Reusable cognition logical reference")
        _text(self.logical_generation, "Reusable cognition logical generation")
        _digest(self.source_digest, "Reusable cognition source digest")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-reusable-cognition-reference",
            "role": self.role,
            "logicalRef": self.logical_ref,
            "logicalGeneration": self.logical_generation,
            "sourceDigest": self.source_digest,
        }
        validate_json_value(value)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "HarnessReusableCognitionReference":
        if set(value) != {
            "schemaVersion",
            "kind",
            "role",
            "logicalRef",
            "logicalGeneration",
            "sourceDigest",
        }:
            raise ValueError("HarnessReusableCognitionReference fields differ")
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-reusable-cognition-reference"
        ):
            raise ValueError("HarnessReusableCognitionReference identity is invalid")
        return cls(
            role=value["role"],
            logical_ref=value["logicalRef"],
            logical_generation=value["logicalGeneration"],
            source_digest=value["sourceDigest"],
        )


@dataclass(frozen=True, slots=True)
class HarnessReusableCognitionSelection:
    """Caller/Agent application selection of one reusable source into one seed slot."""

    slot: str
    reference: HarnessReusableCognitionReference

    def __post_init__(self) -> None:
        _text(self.slot, "Reusable cognition seed slot", max_bytes=160)
        if not isinstance(self.reference, HarnessReusableCognitionReference):
            raise TypeError("Reusable cognition selection requires an exact reference")


class ReusableCognitionSourceResolver(Protocol):
    """External owner/application resolver for one exact reusable source.

    Harness owns neither the resolver nor its repository. The returned source is
    mechanically checked against the exact reference before a cognition seed is
    produced.
    """

    def resolve(
        self,
        reference: HarnessReusableCognitionReference,
    ) -> HarnessWorkingViewSource: ...


def resolve_reusable_cognition_source(
    reference: HarnessReusableCognitionReference,
    resolver: ReusableCognitionSourceResolver,
) -> HarnessWorkingViewSource:
    """Resolve and verify one exact external source without storing or selecting it."""

    source = resolver.resolve(reference)
    if not isinstance(source, HarnessWorkingViewSource):
        raise TypeError("Reusable cognition resolver must return HarnessWorkingViewSource")
    if source.logical_ref != reference.logical_ref:
        raise ValueError("Reusable cognition source logical reference differs")
    if source.logical_generation != reference.logical_generation:
        raise ValueError("Reusable cognition source logical generation differs")
    if source.digest != reference.source_digest:
        raise ValueError("Reusable cognition source digest differs")
    return source


def compile_reusable_cognition_seed(
    *,
    attempt_id: str,
    selections: tuple[HarnessReusableCognitionSelection, ...],
    basis: str,
    resolver: ReusableCognitionSourceResolver,
) -> HarnessCognitionSeed:
    """Compile explicit external selections into the existing exact seed path.

    This is intentionally a pure resolution/admission helper. It performs no
    search/ranking and touches no Harness Store. The returned seed is later
    materialized by the normal Harness cognition path, where Run privacy and
    WorkingSet authority are enforced exactly as for caller-authored sources.
    """

    if not selections:
        raise ValueError("Reusable cognition seed requires at least one selection")
    slots = [selection.slot for selection in selections]
    if len(slots) != len(set(slots)):
        raise ValueError("Reusable cognition seed slots must be unique")
    ordered = tuple(sorted(selections, key=lambda selection: selection.slot))
    sources = tuple(
        HarnessCognitionSeedSource(
            slot=selection.slot,
            source=resolve_reusable_cognition_source(selection.reference, resolver),
        )
        for selection in ordered
    )
    return HarnessCognitionSeed(attempt_id=attempt_id, sources=sources, basis=basis)


def effective_knowledge_topology() -> dict[str, JsonValue]:
    """Project the current knowledge/cognition topology without adding authority."""

    value: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-knowledge-topology",
        "truthRole": "derived-knowledge-topology-projection",
        "laws": [
            "canonical history does not imply current cognition",
            "storage persistence does not imply cognition persistence",
            "reusable source presence does not imply selection",
            "procedure classification does not imply correctness or Tool authority",
            "external semantic promotion does not imply Run admission",
        ],
        "layers": [
            {
                "layerId": "canonical-history",
                "owner": "harness-journal-cas",
                "scope": "run",
                "role": "exact recovery/evidence chronology",
                "modelVisible": "not-implied",
            },
            {
                "layerId": "episodic-recall",
                "owner": "harness-run-continuity",
                "scope": "same-run-committed-working-set-identities",
                "role": "bounded exact historical cognition identity recall",
                "semanticSearch": False,
            },
            {
                "layerId": "reusable-external-source",
                "owner": "application-host-domain",
                "scope": "cross-run-or-project",
                "role": "exact knowledge/procedure source available for explicit selection",
                "automaticInjection": False,
            },
            {
                "layerId": "durable-current-cognition",
                "owner": "agent-selected-working-set",
                "scope": "run",
                "role": "exact selected sources projected to the model",
                "selectionRequired": True,
            },
            {
                "layerId": "interaction-cognition",
                "owner": "caller-ingress-authority",
                "scope": "current-interaction",
                "role": "exact caller replies until interaction boundary",
                "durablePromotion": "explicit-agent-action-only",
            },
            {
                "layerId": "attempt-cognition",
                "owner": "provider-tool-continuity",
                "scope": "current-attempt",
                "role": "Provider-authored Tool exchange and transient attempt state",
                "successorRetention": False,
            },
            {
                "layerId": "procedural-capital",
                "owner": "external-procedure-owner-and-evaluator",
                "scope": "cross-run-or-project",
                "role": "procedure-role reusable source after external promotion",
                "harnessSemanticEvaluation": False,
            },
        ],
        "proceduralCapitalLoop": {
            "candidate": {
                "mechanism": "caller-bound structured completion / CompletionProposal",
                "authority": "bounded-run-candidate-only",
                "automaticPromotion": False,
            },
            "evaluation": {
                "owner": "external-domain-evaluator",
                "harnessSemanticDecision": False,
            },
            "promotion": {
                "owner": "external-reusable-source-owner",
                "canonicalRepresentation": "HarnessWorkingViewSource + exact reusable reference",
            },
            "futureAdmission": {
                "mechanism": "explicit reusable reference selection -> HarnessCognitionSeed",
                "automaticInjection": False,
            },
        },
    }
    validate_json_value(value)
    return value


def effective_knowledge_topology_digest() -> str:
    return canonical_digest(effective_knowledge_topology())


__all__ = [
    "HarnessReusableCognitionReference",
    "HarnessReusableCognitionSelection",
    "ReusableCognitionSourceResolver",
    "compile_reusable_cognition_seed",
    "effective_knowledge_topology",
    "effective_knowledge_topology_digest",
    "resolve_reusable_cognition_source",
]
