"""Task-conditioned capability discovery without capability authority.

The inputs to this module are already-published capability descriptors. Discovery
only narrows what a caller or Agent may inspect. It does not grant a Tool, mint
owner currentness, or turn descriptor relevance into execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from anc_canonical import JsonValue, canonical_digest, validate_json_value

_ALLOWED_ACTION_KINDS = frozenset({"tool", "native", "reference"})
_ALLOWED_STANDINGS = frozenset({"AVAILABLE", "BLOCKED", "UNKNOWN"})
_TOKEN = re.compile(r"[\w.:-]+", re.UNICODE)


def _text(value: Any, label: str, *, max_bytes: int = 2048) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _texts(
    values: tuple[str, ...],
    label: str,
    *,
    max_items: int = 32,
    max_bytes: int = 512,
) -> tuple[str, ...]:
    if len(values) > max_items:
        raise ValueError(f"{label} exceeds {max_items} items")
    checked = tuple(_text(value, label, max_bytes=max_bytes) for value in values)
    if len(checked) != len(set(checked)):
        raise ValueError(f"{label} values must be unique")
    return checked


def _normalized(value: str) -> str:
    return value.casefold().strip()


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    capability_id: str
    owner: str
    summary: str
    source_ref: str
    source_version: str
    action_kind: str
    action_name: str
    effect_class: str = "OWNER_DEFINED"
    tags: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    authority_requirements: tuple[str, ...] = ()
    currentness_requirements: tuple[str, ...] = ()
    visibility: str = "discoverable"

    def __post_init__(self) -> None:
        _text(self.capability_id, "capability id", max_bytes=512)
        _text(self.owner, "capability owner", max_bytes=256)
        _text(self.summary, "capability summary")
        _text(self.source_ref, "capability source ref", max_bytes=1024)
        _text(self.source_version, "capability source version", max_bytes=512)
        if self.action_kind not in _ALLOWED_ACTION_KINDS:
            raise ValueError(
                "capability action kind must be tool, native, or reference"
            )
        _text(self.action_name, "capability action name", max_bytes=512)
        _text(self.effect_class, "capability effect class", max_bytes=256)
        _texts(self.tags, "capability tag", max_items=32, max_bytes=256)
        _texts(self.requirements, "capability requirement")
        _texts(self.authority_requirements, "capability authority requirement")
        _texts(self.currentness_requirements, "capability currentness requirement")
        _text(self.visibility, "capability visibility", max_bytes=160)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "capabilityId": self.capability_id,
            "owner": self.owner,
            "summary": self.summary,
            "source": {
                "ref": self.source_ref,
                "version": self.source_version,
            },
            "action": {
                "kind": self.action_kind,
                "name": self.action_name,
            },
            "effectClass": self.effect_class,
            "visibility": self.visibility,
        }
        if self.tags:
            value["tags"] = list(self.tags)
        if self.requirements:
            value["requirements"] = list(self.requirements)
        if self.authority_requirements:
            value["authorityRequirements"] = list(self.authority_requirements)
        if self.currentness_requirements:
            value["currentnessRequirements"] = list(self.currentness_requirements)
        validate_json_value(value)
        return value


@dataclass(frozen=True, slots=True)
class CapabilityDiscoveryQuery:
    intent: str
    terms: tuple[str, ...] = ()
    owner_hints: tuple[str, ...] = ()
    max_candidates: int = 8

    def __post_init__(self) -> None:
        _text(self.intent, "capability discovery intent", max_bytes=1024)
        _texts(self.terms, "capability discovery term", max_items=32, max_bytes=256)
        _texts(self.owner_hints, "capability owner hint", max_items=16, max_bytes=256)
        if type(self.max_candidates) is not int or not 1 <= self.max_candidates <= 64:
            raise ValueError("capability max candidates must be an integer from 1 to 64")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "intent": self.intent,
            "terms": list(self.terms),
            "ownerHints": list(self.owner_hints),
            "maxCandidates": self.max_candidates,
        }


@dataclass(frozen=True, slots=True)
class CapabilityCandidate:
    capability_id: str
    owner: str
    summary: str
    action_kind: str
    action_name: str
    effect_class: str
    source_ref: str
    source_version: str
    descriptor_digest: str
    matched_terms: tuple[str, ...]
    owner_hint_matched: bool

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "capabilityId": self.capability_id,
            "owner": self.owner,
            "summary": self.summary,
            "stage": "candidate",
            "action": {"kind": self.action_kind, "name": self.action_name},
            "effectClass": self.effect_class,
            "source": {"ref": self.source_ref, "version": self.source_version},
            "descriptorDigest": self.descriptor_digest,
            "matchedTerms": list(self.matched_terms),
            "ownerHintMatched": self.owner_hint_matched,
            "claims": {
                "authorityGranted": False,
                "currentnessProven": False,
                "executionAdmitted": False,
            },
        }
        validate_json_value(value)
        return value


@dataclass(frozen=True, slots=True)
class CapabilityCandidateSet:
    query: CapabilityDiscoveryQuery
    candidates: tuple[CapabilityCandidate, ...]
    corpus_count: int
    matched_count: int
    corpus_digest: str

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-capability-candidate-set",
            "truthRole": "task-conditioned-discovery-not-authority",
            "query": self.query.to_dict(),
            "corpusCount": self.corpus_count,
            "matchedCount": self.matched_count,
            "returnedCount": len(self.candidates),
            "omittedMatchedCount": self.matched_count - len(self.candidates),
            "corpusDigest": self.corpus_digest,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "claims": {
                "rankingIsSemanticAuthority": False,
                "authorityGranted": False,
                "toolSurfaceExpanded": False,
            },
        }
        validate_json_value(value)
        return value


def _query_terms(query: CapabilityDiscoveryQuery) -> tuple[str, ...]:
    values = list(query.terms)
    values.extend(token for token in _TOKEN.findall(query.intent) if len(token) >= 3)
    normalized: list[str] = []
    for value in values:
        term = _normalized(value)
        if term and term not in normalized:
            normalized.append(term)
    return tuple(normalized)


def _descriptor_haystack(descriptor: CapabilityDescriptor) -> str:
    return " \n".join(
        (
            descriptor.capability_id,
            descriptor.owner,
            descriptor.summary,
            descriptor.action_name,
            descriptor.effect_class,
            *descriptor.tags,
        )
    ).casefold()


def discover_capabilities(
    descriptors: tuple[CapabilityDescriptor, ...],
    query: CapabilityDiscoveryQuery,
) -> CapabilityCandidateSet:
    """Return bounded task-conditioned candidates from caller-owned descriptors."""

    by_id = {descriptor.capability_id: descriptor for descriptor in descriptors}
    if len(by_id) != len(descriptors):
        raise ValueError("capability descriptor ids must be unique")
    ordered_descriptors = tuple(by_id[key] for key in sorted(by_id))
    corpus_digest = canonical_digest([item.to_dict() for item in ordered_descriptors])
    terms = _query_terms(query)
    explicit_terms = tuple(_normalized(term) for term in query.terms)
    owner_hints = {_normalized(owner) for owner in query.owner_hints}

    matches: list[tuple[bool, int, str, CapabilityCandidate]] = []
    for descriptor in ordered_descriptors:
        haystack = _descriptor_haystack(descriptor)
        matched = tuple(term for term in terms if term in haystack)
        matched_explicit = tuple(term for term in explicit_terms if term in haystack)
        owner_match = _normalized(descriptor.owner) in owner_hints
        if explicit_terms:
            text_admitted = bool(matched_explicit)
        else:
            text_admitted = bool(matched)
        if not text_admitted and not owner_match:
            continue
        candidate = CapabilityCandidate(
            capability_id=descriptor.capability_id,
            owner=descriptor.owner,
            summary=descriptor.summary,
            action_kind=descriptor.action_kind,
            action_name=descriptor.action_name,
            effect_class=descriptor.effect_class,
            source_ref=descriptor.source_ref,
            source_version=descriptor.source_version,
            descriptor_digest=descriptor.digest,
            matched_terms=matched,
            owner_hint_matched=owner_match,
        )
        matches.append((owner_match, len(matched), descriptor.capability_id, candidate))

    matches.sort(key=lambda item: (not item[0], -item[1], item[2]))
    selected = tuple(item[3] for item in matches[: query.max_candidates])
    return CapabilityCandidateSet(
        query=query,
        candidates=selected,
        corpus_count=len(descriptors),
        matched_count=len(matches),
        corpus_digest=corpus_digest,
    )


def _inspection_value(descriptor: CapabilityDescriptor) -> dict[str, JsonValue]:
    value: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-capability-inspection",
        "truthRole": "exact-descriptor-inspection-not-authority",
        "stage": "inspected",
        "descriptorDigest": descriptor.digest,
        "descriptor": descriptor.to_dict(),
        "claims": {
            "authorityGranted": False,
            "currentnessProven": False,
            "executionAdmitted": False,
        },
    }
    validate_json_value(value)
    return value


def inspect_capability(
    descriptors: tuple[CapabilityDescriptor, ...],
    candidate: CapabilityCandidate,
) -> dict[str, JsonValue]:
    """Resolve one exact candidate to its full current descriptor bytes."""

    matches = [item for item in descriptors if item.capability_id == candidate.capability_id]
    if len(matches) != 1:
        raise ValueError("capability candidate does not resolve to one exact descriptor")
    descriptor = matches[0]
    if descriptor.digest != candidate.descriptor_digest:
        raise ValueError("capability descriptor changed after candidate discovery")
    return _inspection_value(descriptor)


def inspect_capability_id(
    descriptors: tuple[CapabilityDescriptor, ...], capability_id: str
) -> dict[str, JsonValue]:
    """Inspect one exact caller-named descriptor without a discovery side effect."""

    _text(capability_id, "capability id", max_bytes=512)
    matches = [item for item in descriptors if item.capability_id == capability_id]
    if len(matches) != 1:
        raise ValueError("capability id does not resolve to one exact descriptor")
    return _inspection_value(matches[0])


@dataclass(frozen=True, slots=True)
class CapabilityStanding:
    capability_id: str
    standing: str
    evidence_refs: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.capability_id, "capability standing id", max_bytes=512)
        if self.standing not in _ALLOWED_STANDINGS:
            raise ValueError(
                "capability standing must be AVAILABLE, BLOCKED, or UNKNOWN"
            )
        _texts(self.evidence_refs, "capability standing evidence ref", max_items=32)
        _texts(self.reasons, "capability standing reason", max_items=32)


@dataclass(frozen=True, slots=True)
class CapabilityAffordance:
    candidate: CapabilityCandidate
    standing: CapabilityStanding
    action_admitted: bool
    can_invoke_now: bool

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "capabilityId": self.candidate.capability_id,
            "owner": self.candidate.owner,
            "summary": self.candidate.summary,
            "stage": "current-affordance",
            "action": {
                "kind": self.candidate.action_kind,
                "name": self.candidate.action_name,
                "admitted": self.action_admitted,
                "canInvokeNow": self.can_invoke_now,
            },
            "standing": self.standing.standing,
            "effectClass": self.candidate.effect_class,
            "standingEvidenceRefs": list(self.standing.evidence_refs),
            "reasons": list(self.standing.reasons),
            "descriptorDigest": self.candidate.descriptor_digest,
        }
        validate_json_value(value)
        return value


@dataclass(frozen=True, slots=True)
class CapabilityAffordanceSet:
    candidate_set_digest: str
    affordances: tuple[CapabilityAffordance, ...]
    admitted_action_names: tuple[str, ...]
    selected_action_names: tuple[str, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-current-capability-affordances",
            "truthRole": "compiled-from-candidates-standing-and-existing-admission",
            "candidateSetDigest": self.candidate_set_digest,
            "admittedActionNames": list(self.admitted_action_names),
            "selectedActionNames": list(self.selected_action_names),
            "affordances": [item.to_dict() for item in self.affordances],
            "claims": {
                "ownerTruthMinted": False,
                "currentnessMinted": False,
                "authorityExpanded": False,
                "candidateImpliesAvailability": False,
            },
        }
        validate_json_value(value)
        return value

    def to_model_dict(self) -> dict[str, JsonValue]:
        """Project only load-bearing actionability facts for model consumption.

        ``to_dict()`` remains the exact audit/debug carrier with summaries, evidence
        references, reasons and descriptor digests. The model projection deliberately
        does not replay those bytes on every turn: Tool definitions already carry
        callable semantics, while this projection adds only the standing/admission
        information that Tool schemas cannot establish. Exact inspection remains an
        on-demand operation rather than implicit context.
        """

        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-current-capability-affordances-compact",
            "truthRole": "compiled-model-navigation-not-owner-truth",
            "candidateSetDigest": self.candidate_set_digest,
            "candidates": [
                {
                    "capabilityId": item.candidate.capability_id,
                    "owner": item.candidate.owner,
                    "action": {
                        "kind": item.candidate.action_kind,
                        "name": item.candidate.action_name,
                    },
                    "standing": item.standing.standing,
                    "admitted": item.action_admitted,
                    "canInvokeNow": item.can_invoke_now,
                }
                for item in self.affordances
            ],
            "claims": {
                "ownerTruthMinted": False,
                "currentnessMinted": False,
                "authorityExpanded": False,
                "candidateImpliesAvailability": False,
                "exactEvidenceElided": True,
            },
        }
        validate_json_value(value)
        return value


def compile_capability_affordances(
    candidate_set: CapabilityCandidateSet,
    descriptors: tuple[CapabilityDescriptor, ...],
    standings: tuple[CapabilityStanding, ...],
    *,
    admitted_action_names: tuple[str, ...],
) -> CapabilityAffordanceSet:
    """Compile candidates against supplied standing and existing action admission."""

    if len(admitted_action_names) != len(set(admitted_action_names)):
        raise ValueError("admitted capability action names must be unique")
    descriptor_by_id = {item.capability_id: item for item in descriptors}
    if len(descriptor_by_id) != len(descriptors):
        raise ValueError("capability descriptor ids must be unique")
    standing_by_id = {item.capability_id: item for item in standings}
    if len(standing_by_id) != len(standings):
        raise ValueError("capability standing ids must be unique")

    admitted = set(admitted_action_names)
    affordances: list[CapabilityAffordance] = []
    selected: set[str] = set()
    for candidate in candidate_set.candidates:
        descriptor = descriptor_by_id.get(candidate.capability_id)
        if descriptor is None or descriptor.digest != candidate.descriptor_digest:
            raise ValueError(
                "capability candidate cannot compile against changed/missing descriptor"
            )
        standing = standing_by_id.get(candidate.capability_id)
        if standing is None:
            standing = CapabilityStanding(
                candidate.capability_id,
                "UNKNOWN",
                reasons=("current standing not supplied by an owning authority",),
            )
        action_admitted = (
            descriptor.action_kind != "reference"
            and descriptor.action_name in admitted
        )
        can_invoke = standing.standing == "AVAILABLE" and action_admitted
        if can_invoke:
            selected.add(descriptor.action_name)
        affordances.append(
            CapabilityAffordance(
                candidate=candidate,
                standing=standing,
                action_admitted=action_admitted,
                can_invoke_now=can_invoke,
            )
        )

    selected_names = tuple(name for name in admitted_action_names if name in selected)
    return CapabilityAffordanceSet(
        candidate_set_digest=candidate_set.digest,
        affordances=tuple(affordances),
        admitted_action_names=admitted_action_names,
        selected_action_names=selected_names,
    )


def descriptors_from_effective_catalog() -> tuple[CapabilityDescriptor, ...]:
    """Flatten current source-derived Harness catalog into discoverable actions."""

    from .capability_catalog import (
        effective_capability_catalog,
        effective_capability_catalog_digest,
    )

    catalog = effective_capability_catalog()
    version = effective_capability_catalog_digest()
    descriptors: list[CapabilityDescriptor] = []
    for surface in catalog["executionSurfaces"]:
        source = surface["source"]
        requirements = surface["requirements"]
        for tool in surface["tools"]:
            descriptors.append(
                CapabilityDescriptor(
                    capability_id=(
                        f"{surface['surfaceId']}.tool.{tool['name']}"
                    ),
                    owner=str(surface["owner"]),
                    summary=(
                        f"{tool['description']} Surface: {surface['summary']}"
                    ),
                    source_ref=str(source["surfaceSymbol"]),
                    source_version=version,
                    action_kind="tool",
                    action_name=str(tool["name"]),
                    effect_class="OWNER_DEFINED_TOOL_EFFECT",
                    tags=(
                        str(surface["surfaceId"]),
                        str(surface["visibility"]),
                        str(tool["name"]),
                    ),
                    authority_requirements=tuple(
                        f"{key}={value}" for key, value in requirements.items()
                    ),
                    currentness_requirements=(
                        "external owner/runtime currentness remains outside catalog discovery",
                    ),
                    visibility=str(surface["visibility"]),
                )
            )
    for mechanism in catalog["cognitionMechanisms"]:
        descriptors.append(
            CapabilityDescriptor(
                capability_id=str(mechanism["capabilityId"]),
                owner=str(mechanism["owner"]),
                summary=str(mechanism["summary"]),
                source_ref=f"catalog://{mechanism['capabilityId']}",
                source_version=version,
                action_kind="native",
                action_name=str(mechanism["requestField"]),
                effect_class="HARNESS_COGNITION_OR_CONCLUSION_ACTION",
                tags=(str(mechanism["requestField"]), "cognition"),
                requirements=tuple(
                    str(item)
                    for item in (
                        list(mechanism["runRequirements"])
                        + list(mechanism["turnRequirements"])
                    )
                ),
                authority_requirements=(
                    "exact AgentTurnRequest capability must admit this action",
                ),
                visibility="recommended-or-profile-bound",
            )
        )
    program = catalog["programmaticToolComposition"]
    descriptors.append(
        CapabilityDescriptor(
            capability_id="harness.action.tool-program",
            owner="ordivon-harness",
            summary=(
                "Compose a bounded linear program over exact Tools admitted on the current turn."
            ),
            source_ref="catalog://programmaticToolComposition",
            source_version=version,
            action_kind="native",
            action_name=str(program["modelAction"]),
            effect_class="COMPOSES_ALREADY_ADMITTED_TOOL_EFFECTS",
            tags=("tool program", "composition", "programmatic tool calling"),
            authority_requirements=(
                "exact current AgentTurnRequest Tools only",
                "positive existing physical Tool budget",
            ),
            currentness_requirements=(
                "current turn Tool admission remains authoritative",
            ),
            visibility=str(program["visibility"]),
        )
    )
    observation = catalog["sourceFencedObservationComposition"]
    descriptors.append(
        CapabilityDescriptor(
            capability_id="harness.composition.source-fenced-observation",
            owner="ordivon-harness",
            summary=(
                "Build an observation-only search/read Tool surface bound to exact source and optional owner authority evidence."
            ),
            source_ref=str(observation["surfaceFactory"]),
            source_version=version,
            action_kind="reference",
            action_name=str(observation["surfaceFactory"]),
            effect_class="OBSERVATION_ONLY_COMPOSITION",
            tags=("observation", "search", "read", "source fence"),
            authority_requirements=(
                "caller must bind exact source/grant authority before Run admission",
            ),
            currentness_requirements=(
                "Harness does not mint owner/currentness truth",
            ),
            visibility=str(observation["visibility"]),
        )
    )
    return tuple(sorted(descriptors, key=lambda item: item.capability_id))


__all__ = [
    "CapabilityAffordance",
    "CapabilityAffordanceSet",
    "CapabilityCandidate",
    "CapabilityCandidateSet",
    "CapabilityDescriptor",
    "CapabilityDiscoveryQuery",
    "CapabilityStanding",
    "compile_capability_affordances",
    "descriptors_from_effective_catalog",
    "discover_capabilities",
    "inspect_capability",
    "inspect_capability_id",
]
