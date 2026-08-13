# Ordivon Harness P1 reusable knowledge / procedural capital closeout

> **Historical implementation evidence:** This document records the P1 cross-Run cognition/procedural-capital experiment. Current product boundaries live in [`../README.md`](../README.md), [`STATUS.md`](STATUS.md), [`COMPATIBILITY.md`](COMPATIBILITY.md), and [`authority.md`](authority.md).

## Question

P-C1 already proved and implemented within-Run durable cognition: WorkingSet selection, caller promotion, attempt-local cognition, historical pin recall and exact supersession. P1 therefore did **not** ask for a generic Memory system. It asked one missing transition:

> How can externally owned knowledge or a promoted procedure be reused across independent Runs while preserving exact provenance, explicit selection, Run privacy and external semantic authority?

Baseline revision was `321ce5c006b6a28a9f44055688e66d0c3b6b8c09`.

## Baseline

The existing `HarnessCognitionSeed` could carry exact caller-authored `HarnessWorkingViewSource` values into a new Run, but the caller had to reconstruct those values per Run. A raw seed can legitimately contain changed bytes under the same logical reference/generation because Harness has no external canonical object to compare against. That is valid local cognition, but it cannot prove reuse of one canonical cross-Run procedure.

Focused baseline cognition/composition tests passed **37/37** before treatment.

## Accepted topology

P1 keeps these layers distinct:

```text
Canonical History         Harness Journal/CAS, one Run
Episodic Recall           exact prior committed WorkingSet identities, same Run
Reusable External Source application/Host/domain-owned, cross-Run/project
Current Durable Cognition Agent-selected WorkingSet, one Run
Interaction Cognition     caller ingress, current interaction
Attempt Cognition         Provider/Tool exchange, current attempt
Procedural Capital        externally evaluated/promoted reusable source
```

The retained laws are:

```text
History ≠ Cognition
Storage persistence ≠ Cognition persistence
Reusable source presence ≠ Selection
Procedure role ≠ Correctness
Procedure role ≠ Tool authority
External semantic promotion ≠ Run admission
```

## Minimal reusable-source seam

Advanced `ordivon_harness.knowledge_topology` adds:

- `HarnessReusableCognitionReference`: role + owner-qualified logical reference + logical generation + exact `HarnessWorkingViewSource` digest;
- `HarnessReusableCognitionSelection`: an explicit seed slot plus exact reference;
- `ReusableCognitionSourceResolver`: application/Host/domain-owned resolution interface;
- `resolve_reusable_cognition_source()`: verifies exact logical identity/generation/digest;
- `compile_reusable_cognition_seed()`: pure explicit reference-to-existing-`HarnessCognitionSeed` compilation;
- `effective_knowledge_topology()`: read-only ownership/topology projection included in the P0 generated capability catalog.

The seam owns no repository, search, ranking, evaluation or promotion policy and touches no Harness Store during resolution. After compilation, the existing cognition path performs normal privacy validation, CAS materialization and WorkingSet selection.

A reusable reference/resolver is never automatically attached to a Run. A cognition-enabled Run without an explicit initial seed still fails before Provider dispatch.

## Procedural capital without a Skill store

P1 tested whether Harness needed a new `SkillCandidate -> evaluate -> promote -> Skill` state machine. It did not.

Existing caller-bound structured completion already provides the candidate outlet:

```text
bounded Run experience
  -> structured procedure candidate + evidence refs + unresolved unknowns
  -> external evaluator
  -> external canonical promotion
  -> HarnessWorkingViewSource
  -> exact HarnessReusableCognitionReference(role="procedure")
  -> future explicit compile_reusable_cognition_seed()
  -> existing Run privacy/CAS/WorkingSet
```

A P1 fixture used a structured procedure-candidate schema containing task class, procedure, validity conditions, claimed benefit and falsifier. The external evaluator fixture rejected candidates with unresolved unknowns or no independent evidence. Only an accepted external promotion produced the canonical reusable source/reference.

This preserves the existing rule that `CompletionProposal`/structured completion is a **candidate for caller/domain verification**, not semantic completion or automatic persistent learning.

## Ablation result

### Retain

- explicit knowledge topology;
- exact reusable external reference + resolver + selection;
- reference-to-existing-seed compiler;
- P0 capability catalog projection of knowledge topology;
- existing structured completion / CompletionProposal as procedural-candidate outlet;
- external evaluation/promotion followed by exact future admission.

### Shrink

The P1 module remains advanced and packaged, not a stable package-root / `ordivon_harness.api` export. Cross-Run storage/repository/discovery/ranking remains external. The only Harness-owned addition is exact admission/projection around existing cognition machinery.

### Reject / delete

P1 does not add:

- generic Memory CRUD;
- vector/RAG semantic ranking;
- automatic memory/skill extraction from conversation or Tool text;
- hidden cross-Run injection;
- Harness-owned knowledge repository;
- Harness-owned `SkillCandidate` or `Skill` persistence;
- model-self-reflection promotion directly into canonical procedure state;
- Harness semantic evaluator/promotion policy;
- a second cognition materialization path.

## Evidence

Treatment evidence before full repository acceptance:

- reusable-source tests: exact reference round-trip, drift rejection, two independent Run reuse, no-auto-injection, existing privacy, duplicate-slot rejection;
- baseline-red/treatment-green ablation: raw seed cannot prove canonical external procedure identity; exact reference rejects changed bytes;
- procedural-capital tests: existing structured completion candidate outlet, unresolved candidate rejection, no-evidence rejection, external ownership projection;
- focused P1/P0/structured-completion regression: **21/21 passed**;
- broader P1 cognition treatment regression: **28/28 passed**.

Final release acceptance also passed: **367 tests, 3 skipped**, isolated Ruff/compile, dependency/documentation/evidence contracts, deterministic demo, and isolated wheel build/install with the stable package-root API unchanged. Full acceptance Runtime Job: `job-019ffc14-1ee2-7c13-8c36-171a40e48e55`. Wheel gate: `job-019ffc15-bf5e-7a23-89cb-1d9060ba3d2f`.

## Result

P1 establishes **Work -> Candidate -> External Evaluation -> External Promotion -> Reusable Exact Source -> Future Explicit Cognition** without turning Harness into a Memory/Skill platform.

The resulting boundary is deliberately asymmetric:

> Harness makes cross-Run knowledge/procedure reuse exact and admissible; it does not decide what deserves to become knowledge or a procedure.
