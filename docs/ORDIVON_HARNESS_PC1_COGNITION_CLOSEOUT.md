# Ordivon Harness P-C1 cognition closeout

> **Historical research closeout:** This document records the P-C1.1–P-C1.12 experimental path that established the current Harness cognition model. It explains why the current architecture exists, but it is not an independent source of current authority. Use [`../README.md`](../README.md), [`../ARCHITECTURE.md`](../ARCHITECTURE.md), [`STATUS.md`](STATUS.md), [`DATA_AND_PRIVACY.md`](DATA_AND_PRIVACY.md), and [`authority.md`](authority.md) for active behavior and ownership. Exact bounded claims remain indexed in [`../evidence/index.json`](../evidence/index.json).

## Closure decision

P-C1 is closed as a **world-model and mechanism line**, not because every future cognition problem is solved. The line established the minimum structural laws required for Agent-owned cognition to be durable, selectable, recoverable and executable without turning Harness into a semantic Memory/RAG policy engine.

The final product model is:

> **Harness makes Agent cognition executable.**
>
> The Agent owns semantic reasoning, cognition selection and action choice. Harness owns exact identity, provenance, continuity, action admission and recoverable state/effect transitions.

The research line should be reopened only when a real workload exposes an Agent-required cognition state transition that cannot be lawfully expressed with the current mechanisms. It should not be extended merely because a familiar framework category such as Memory, RAG, context management or semantic versioning exists elsewhere.

## What P-C1 replaced

The initial implicit model was effectively:

```text
HarnessRunState.messages
  ├─ durable recovery history
  └─ model-visible context
```

That model conflated too many independent facts. The closed model is:

```text
Canonical History
  │
  ├─ Agent-selected Durable Cognition / WorkingSet
  ├─ Caller-owned Interaction Cognition
  └─ Attempt-local Provider/Tool Cognition
          │
          ▼
   Effective Model View
          │
   + Execution Control
          │
          ▼
        Agent
          │
   cognition / action / conclusion
          │
          ▼
      new durable evidence
```

The important result is not the names of these structures. It is that **occurred, stored, observed, selected, current, executable and physically effected are no longer represented as one fact**.

## Experimental trajectory

### P-C1.1 — History / WorkingSet / WorkingView separation

Established that canonical durable recovery history and model-visible cognition are different authorities. A committed WorkingSet selects exact source objects; a WorkingView is deterministically compiled from that selection; the Provider receives the WorkingView rather than the complete historical transcript.

**Law:** `History ≠ Cognition`.

### P-C1.2a — Privacy as state authority

Removed hidden durable content paths from metadata-only continuity. Exact model/Tool content is retained only when the Run Contract authorizes it; digest-only evidence can still fence effects but cannot reconstruct omitted cognition.

**Law:** recovery cannot manufacture bytes that privacy authority deliberately did not retain.

### P-C1.2b — Mature multi-turn projection

Moved WorkingView projection into the real Agent loop and fenced projection/dispatch races. This proved model view can evolve independently from canonical Run history without adding RAG, ranking or automatic replanning.

**Law:** the exact effective model view is a first-class execution fact.

### P-C1.3 — Agent-owned WorkingSet transition

Introduced an Agent cognition action distinct from Runtime Tool effects and Run conclusion. The Agent chooses exact successor pins; Harness performs the atomic `replan → select → commit` transition with replay and concurrent-writer protection.

**Law:** Agent chooses target cognition state; Harness guarantees lawful state transition.

### P-C1.4 — Discovery / selection boundary

Proved that a domain/World/Runtime integration may discover or materialize candidate sources without granting them current cognition authority. Harness does not convert discovery into relevance.

**Law:** `Discovery ≠ Selection`; `Storage ≠ Cognition`.

### P-C1.5 — Epistemic control and Provider-faithful Tool cognition

Real DeepSeek experiments falsified the idea that a bare Tool observation is sufficient model cognition. Exact Tool continuity requires the Provider-authored assistant tool-call message followed by the bound Tool result. Execution-control metadata was separated from task Context.

**Law:** effect limits bound external action; they do not author an epistemic conclusion for the Agent.

### P-C1.6 — Cross-process transient cognition continuity

Proved that a fresh process can reconstruct unfinished current-attempt Provider/Tool cognition from existing durable Provider/Tool authority, without introducing a generic Conversation Store.

**Law:** attempt-local cognition can be transient in semantic lifetime while still recoverable from durable evidence.

### P-C1.7 — Durable knowledge promotion boundary

Generalized recovery to ordinary clean pause/resume and proved that an already-materialized source becomes durable cognition only when the Agent explicitly selects it in a successor WorkingSet.

**Law:** `storage persistence ≠ cognition persistence`; observation/materialization does not automatically create Memory.

### P-C1.8 — Historical cognition recall

Added an explicit bounded Agent control that exposes earlier committed WorkingSet identities/pins, not historical source bytes or semantic search results. The Agent may then re-select an exact pin through the ordinary transition path.

**Law:** recall is Agent-owned inspection plus selection, not silent relevance injection.

### P-C1.9 — Attempt identity / cognition progress separation

Proved that a new attempt with identical selected pins is a lawful cognition reset because it changes transient-cognition lifetime, but it is not structural cognition progress and must not reopen exhausted effect gates.

**Law:** `attempt change ≠ cognition change ≠ progress`.

### P-C1.10 — Caller interaction cognition

Separated exact caller replies after `needs_input` from both durable WorkingSet cognition and Tool cognition. Caller ingress survives WorkingSet transitions within the interaction and expires at the next interaction boundary.

**Law:** `Caller Input ≠ Durable Cognition`.

### P-C1.11 — Interaction → durable cognition promotion

Real DeepSeek experiments falsified a design that required the Agent to restate hidden retained WorkingSet pins. The final promotion action lets the Agent choose exact currently-promotable caller indexes and a new slot; Harness derives exact bytes and mechanically extends the current selection. Further live tests forced caller provenance to become visible and caused unusable promotion capability to be withdrawn when no ingress remains.

**Law:** the Agent chooses what deserves persistence; Harness derives exact bytes/provenance and preserves existing selection mechanically.

### P-C1.12 — Current cognition addressability and correction

Real DeepSeek then exposed the symmetric problem: ordinary WorkingSet retain/drop was impossible when the model could see source content but not the exact current pin identities required by the transition action. Harness now aligns current exact pins with their model-message ranges and exposes that provenance only when transition authority is granted.

A controlled live correction proved:

```text
current [task, RED-9]
+ caller GREEN-42
→ promote GREEN-42
→ current [task, RED-9, GREEN-42]
→ ordinary Agent WorkingSet transition
→ current [task, GREEN-42]
```

RED-9 ceased to be current cognition but remained committed historical cognition. No semantic `supersede_memory` action was required.

**Law:** an Agent action is not genuinely usable unless every authority object the action must reference is lawfully visible/addressable.

## Closed cognition model

P-C1 leaves Harness with four cognition/control layers plus history/effects:

1. **Canonical History** — durable facts about what happened.
2. **Durable Cognition** — Agent-selected WorkingSet sources.
3. **Interaction Cognition** — exact caller ingress for the current interaction.
4. **Attempt Cognition** — Provider-authored Tool exchange for the current cognition attempt.
5. **Execution Control** — current capability truth, budgets and addressable authority/provenance required for lawful Agent decisions.
6. **Effects** — admitted actions and physical consequences owned jointly with Runtime/external authorities.

The effective model view is a projection over cognition, not a synonym for history. Execution control is visible to the Agent but is not task-world evidence.

## Frozen constitutional laws

The line closes with these laws:

1. **History is not cognition.**
2. **Observation is not retention.**
3. **Durable cognition selection belongs to the Agent.**
4. **Semantic meaning belongs to the Agent; structural truth belongs to Harness.**
5. **Authority required for lawful Agent choice must be visible and addressable.**
6. **Cognition, interaction, control and physical effects are separate state domains.**
7. **Recovery restores proven state and never treats uncertainty as redispatch permission.**
8. **Harness adds a cognition mechanism only when an Agent-required state transition cannot otherwise be expressed lawfully.**

A useful set of permanent non-equivalences is:

```text
History ≠ Cognition
Storage ≠ Selection
Observation ≠ Retention
Caller Input ≠ Durable Cognition
Tool Observation ≠ Durable Cognition
Attempt Change ≠ Cognition Change
Cognition Change ≠ Progress
Progress ≠ External Effect
Tool Intent ≠ Physical Effect
Physical Effect ≠ Semantic Success
Source Identity ≠ Source Truth
Provenance ≠ Semantic Validity
Exact Replay ≠ Redispatch
Available Capability ≠ Recommended Action
```

## What was deliberately not built

P-C1 does **not** justify adding:

- a generic Memory CRUD service;
- automatic memory extraction from caller/model/Tool text;
- semantic ranking or relevance scoring inside Harness;
- a vector/RAG subsystem as a default Harness component;
- automatic Context compaction/summarization policy;
- Harness-authored semantic conflict resolution or `superseded_by` graph;
- hidden automatic recall/injection;
- a generic Conversation Store duplicating Provider/Journal authority.

These remain possible mechanisms if future workloads prove a specific otherwise-inexpressible transition. They are not assumed requirements.

## What remains open after closure

These are **not P-C1 bugs**; they are candidate future research questions that require new evidence:

- how a strong Agent bootstraps its initial WorkingSet from a minimal foothold without caller-curated Context;
- how an Agent manages very large source universes/WorkingSets without Harness-owned relevance ranking;
- how cross-Run/project cognition can be discovered and reused while preserving Agent selection authority;
- whether Journal chronology plus transition basis is sufficient to recover semantic lineage such as correction versus temporary deselection;
- what Agent-side metacognitive skills/policies are useful for retain/drop/recall/promotion strategy;
- whether the current internal cognition seams should eventually become a supported public integration surface.

Each question should start with a real workload/counterexample. None should be promoted directly into a subsystem roadmap.

## Evidence chain

The exact P-C1 receipts are indexed under `harness.cognition.*` in [`../evidence/index.json`](../evidence/index.json). The current verified endpoint at closure is:

```text
harness.cognition.pc112-durable-cognition-supersession
implementation: 425373cef659177c2a564242560c9061dd6bb22c
```

Earlier P-C1 receipts remain historical proofs for the revisions they bind. P-C1.12 is not a claim that every Harness subsystem is globally verified by that receipt; it is the latest verified cognition-line endpoint.

## Closure rule

Do not continue with P-C1.13 merely because the next conceptual question is visible. Reopen cognition research only after the complete Harness is reassessed from the canonical world model and a real missing state transition survives that broader comparison.
