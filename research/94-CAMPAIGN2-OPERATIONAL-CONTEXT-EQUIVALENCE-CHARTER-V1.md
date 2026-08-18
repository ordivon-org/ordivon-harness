# 94 — CAMPAIGN 2 CHARTER v1
# Operational Context Equivalence — Decision-Sufficient Views, Provenance & Safe Omission

**Control task:** `task:harness-campaign2-operational-context-equivalence-20260818`  
**Programme:** B — Operational Epistemics  
**Standing effect:** programme-level investigation only. HaF0–HaF61 remain frozen; HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 1. Research question

For a bounded Harness TaskEpisode / decision frontier, when may two different operational Context states or views be treated as interchangeable, when is one merely sufficient for another, and when does omission/substitution/provenance/currentness/lifetime difference invalidate that substitution?

The campaign does **not** ask whether two bodies of text have the same universal meaning or whether two prompts produce the same model output. It asks what Context relation Harness can responsibly state without annexing external/domain truth.

## 2. Prebound frame — Context use is relative

Campaign 2 introduces a technology-neutral **Decision Frontier Contract** `F` only as a research abstraction. `F` binds the bounded operational use for which Context is being evaluated, including as applicable:

- the TaskEpisode / Run decision point;
- the action/claim/control distinction currently at issue;
- explicit required references/discriminants/unknowns supplied by the relevant Agent/caller/domain authority;
- provenance/currentness/authority obligations that must remain visible;
- the continuation horizon over which the Context must remain usable (current turn, current attempt, later Run continuation/recovery, etc.).

Harness does not decide arbitrary domain relevance or truth. If the required discriminants are not externally available or derivable from already-owned Harness operational semantics, the correct result may be `EXTERNAL_DECISION_CONTRACT_REQUIRED` rather than pretending the Context is sufficient.

## 3. Prebound relation stack

Campaign 2 does not assume `ContextEquivalence` is primitive. It prebinds four related questions.

### Axis 0 — Context Projection Standing

Is the Context projection itself admissible?

- `VALID_CONTEXT_PROJECTION`
- `INVALID_CONTEXT_PROJECTION`
- `CONTEXT_PROJECTION_UNDERDETERMINED`

Invalidity includes forged provenance, unauthorized content/authority claims, impossible source/generation bindings, silent currentness claims not supported by evidence, or representation that contradicts the bound projection rules.

### Axis A — Decision Sufficiency Standing

For decision frontier `F`, does Context `C` preserve the information/standing required to resolve the explicitly bound operational discriminants?

- `SUFFICIENT_FOR_F`
- `INSUFFICIENT_FOR_F`
- `SUFFICIENCY_UNDERDETERMINED`
- `EXTERNAL_DECISION_CONTRACT_REQUIRED`

Sufficiency is task/frontier/horizon relative, not content-intrinsic.

### Axis B — Directional substitution

`C2 >=_F C1` means `C2` is a safe operational substitute for `C1` at `F`: every `F`-relevant distinction/obligation that `C1` validly supports remains supported at equal-or-stronger standing in `C2`, and `C2` does not hide an `F`-relevant contradiction, unknown, authority/currentness reduction, or provenance dependency.

This relation is directional and need not be symmetric.

### Axis C — Operational Context Equivalence

`C1 ~=_F C2` is provisionally defined as **mutual safe substitution under the same decision frontier/horizon**:

`C1 >=_F C2` and `C2 >=_F C1`.

This is not byte equality, semantic identity of arbitrary content, or behavioral/model-output equivalence.

## 4. Proposition P2 — Obligation-Relative Context Relation

For bounded operational use `F`, a technology-neutral Context relation can be stated without external truth annexation if the relation is based on **validity + obligation-relative sufficiency + provenance/currentness/lifetime preservation**, rather than on content identity or model behavior.

### P2-A — Validity precedes sufficiency

An invalid or forged Context cannot become sufficient merely by containing more apparently relevant content.

### P2-B — Sufficiency is frontier-relative and directional

A Context may be sufficient for one decision frontier and insufficient for another. `C2` may safely substitute for `C1` without the reverse being true.

### P2-C — Equivalence is derived, not primitive

Operational Context equivalence is mutual safe substitution under a fixed `F`; it is not a universal intrinsic relation between Context objects.

### P2-D — Content equality is neither necessary nor sufficient

Different representations may be equivalent for `F`; identical bytes may fail equivalence when provenance, authority, currentness, dependency or lifetime standing differs in an `F`-relevant way.

### P2-E — Safe omission preserves obligations, not model behavior

Removing material is safe for `F` iff the resulting Context remains valid and preserves every `F`-relevant discriminant/unknown/provenance/currentness/authority obligation. Identical model output is neither required nor sufficient evidence of safe omission.

### P2-F — More Context is not monotonically safer

Adding material can make a Context invalid, create unresolved contradiction, alter authority/currentness standing, or expand the basis of admissible claims. Superset relation alone does not establish sufficiency or equivalence.

### P2-G — Lifetime/retention is horizon-relative

Two Context presentations may be interchangeable for an immediate frontier while not equivalent for a later continuation/recovery horizon if one depends on transient material that will not remain admissibly available.

### P2-H — Known unknowns are part of sufficiency

A sufficient Context must preserve relevant uncertainty/unknown standing. Omitting the fact that a required discriminant is unresolved can create false sufficiency.

## 5. Rival models

### R1 — Byte Identity

Context equivalence is exact byte/message equality.

Predicted failure: false non-equivalence under representation/reordering/reconstruction that preserves every bound operational obligation; false equivalence when identical bytes carry different provenance/currentness standing.

### R2 — Model-Output Equivalence

Contexts are equivalent when the Agent/model returns the same answer/action.

Predicted failure: same output can arise from insufficient/forged Context; different outputs can arise from stochastic/model differences despite identical operational Context standing.

### R3 — Superset Monotonicity

More Context is always at least as sufficient and safe as less Context.

Predicted failure: forged, stale, contradictory or authority-expanding additions can make substitution unsafe or invalid.

### R4 — Provenance Blindness

Only content matters; source/provenance/authority/dependency differences do not affect Context equivalence.

Predicted failure: currentness, permission, evidence-dependency or attribution obligations may make identical content operationally non-interchangeable.

### R5 — Newest Wins

The most recent-looking source automatically supersedes older Context.

Predicted failure: recency does not prove authority, validity, supersession or semantic correction.

### R6 — Lifetime Blindness

If two Contexts are sufficient now, they remain equivalent across future continuation/recovery horizons.

Predicted failure: transient Tool/caller cognition may disappear while a durable selected source remains available.

### R7 — WorkingSet Identity

Current implementation WorkingSet/WorkingView identity is the definition of Context identity/equivalence.

Predicted failure: multiple implementation representations may preserve the same operational obligations, while the same selected WorkingSet can yield different effective model-visible Context because caller ingress/transient Tool evidence differs.

### R8 — Global Semantic Equivalence

Harness can decide task-independent semantic equivalence of arbitrary Context without an explicit bounded decision use.

Predicted failure: relevance/sufficiency depends on externally owned task/domain discriminants; attempting a global relation annexes truth/relevance ownership.

## 6. Prebound falsifier classes

P2 is revised/rejected if any fixture establishes:

### F1 — False substitution

P2 classifies `C2 >=_F C1`, but replacing `C1` with `C2` hides or changes an `F`-required operational distinction, unknown, authority/currentness/provenance standing, or justified action/claim basis.

### F2 — False insufficiency

P2 rejects substitution even though all `F`-relevant operational obligations and standing are preserved under a technology-neutral representation change.

### F3 — Behavioral collapse

The criterion cannot be stated without requiring identical model output/behavior.

### F4 — Domain relevance annexation

Harness must independently decide arbitrary domain relevance/truth rather than consume an explicit decision obligation/discriminant contract.

### F5 — Provenance blindness

The criterion treats same content as equivalent despite an `F`-relevant provenance/authority/currentness/dependency difference.

### F6 — Lifetime blindness

The criterion treats Contexts as equivalent across a horizon where one representation is no longer admissibly available.

### F7 — Non-monotonicity failure

The criterion assumes added Context cannot reduce validity/safety despite forged, contradictory, stale or authority-changing additions.

### F8 — Hidden implementation dependence

The surviving criterion requires concrete WorkingSet/WorkingView/SQLite/Python identities rather than operational facts.

## 7. Destructive fixture matrix

The following fixtures are prebound before analysis/dogfood.

| Fixture | Difference | Primary pressure |
|---|---|---|
| T1 | exact same bytes; one source has grounded provenance, one forged provenance | R1/R4; validity before sufficiency |
| T2 | different serialization/order; same exact grounded sources and F-relevant commitments | R1; false insufficiency |
| T3 | same content; one generation is current, one explicitly superseded | R4/R5; currentness |
| T4 | newer-looking source without authority/supersession edge | R5; recency != currentness |
| T5 | add clearly F-irrelevant grounded material | R3; extra material vs equivalence |
| T6 | add contradictory/unresolved grounded material relevant to F | R3; contradiction must remain visible |
| T7 | omit F-essential discriminant/evidence | false sufficiency |
| T8 | omit duplicate bytes that share same upstream source/dependency | evidence dependency / safe omission |
| T9 | replace two independent corroborating sources with one copied duplicate | provenance/dependency standing |
| T10 | same bytes available transiently and durably; immediate frontier | horizon-relative sufficiency |
| T11 | same as T10 but after attempt/recovery horizon where transient source expires | R6; lifetime difference |
| T12 | caller-ingress bytes vs promoted durable source during same interaction | authority/lifetime distinction |
| T13 | same selected durable Context but different transient Tool exchange | R7; effective Context != WorkingSet alone |
| T14 | different selected Contexts that resolve the same explicit F obligations | representation-independent sufficiency |
| T15 | compression removes exact provenance/unknown needed by F while preserving summary content | safe omission / provenance |
| T16 | forged Context expansion adds apparently useful but unauthorized source | R3; validity non-monotonicity |
| T17 | stale and current conflicting sources both retained, with currentness relation explicit | known contradiction/history preservation |
| T18 | no explicit F/domain discriminants are available for a semantic relevance judgment | R8; external contract required |

## 8. Prebound expected tendencies

These are predictions, not results.

- T1 -> not equivalent; forged projection invalid even with identical bytes.
- T2 -> potentially equivalent if ordering/serialization is not itself bound by `F` and provenance obligations are preserved.
- T3 -> generally non-equivalent for a frontier requiring current state; stale material may remain valid history but insufficient substitute.
- T4 -> recency alone insufficient to establish substitution/supersession.
- T5 -> may remain equivalent for `F`, though model behavior is not predicted identical.
- T6 -> not safely equivalent if the contradiction is F-relevant; Context must preserve the unresolved standing.
- T7 -> insufficient.
- T8 -> potentially safe only if the dropped copy contributes no independent provenance/assurance obligation.
- T9 -> not equivalent when independent corroboration is an explicit F obligation.
- T10 -> potentially equivalent for the immediate frontier.
- T11 -> not equivalent for the later horizon.
- T12 -> may be content-sufficient now but not equivalent across authority/lifetime horizons.
- T13 -> same WorkingSet does not prove equivalent effective operational Context.
- T14 -> potentially mutually sufficient/equivalent for the bounded F.
- T15 -> insufficient when exact provenance/unknown is required.
- T16 -> invalid expansion; more content is not more valid.
- T17 -> may be sufficient if the currentness/conflict relation is preserved; silently deleting the stale contradictor may or may not be safe depending on F/history obligations.
- T18 -> `EXTERNAL_DECISION_CONTRACT_REQUIRED`, not an intrinsic equivalence verdict.

## 9. Evaluation method

### Round 1 — Conceptual destructive reconstruction

Apply P2 and R1–R8 to T1–T18. Explicitly test whether `F` and horizon are necessary, whether equivalence reduces to mutual sufficiency, and where external relevance ownership becomes unavoidable.

### Round 2 — Engineering dogfood only where information-positive

Use existing Harness Context mechanisms without changing code to make P2 pass. Prefer fixtures around projection validation, source generations, WorkingSet/effective-view separation, transient-vs-durable cognition, promotion/history recall and stale transition fencing.

### Round 3 — Owner-boundary + Campaign-1 compatibility audit

Verify that the surviving relation does not make Harness the owner of domain truth/relevance, does not imply model-output invariance, and composes cleanly with Campaign-1 recovery/identity criteria.

### Round 4 — Closeout

Classify:

- `CRITERION_SUPPORTED_IN_SCOPE`
- `CRITERION_REVISED`
- `CRITERION_FALSIFIED`
- `INSUFFICIENT_EVIDENCE`

Separately classify Foundation pressure. No Foundation standing changes automatically.

## 10. Stop conditions

Stop rather than expand scope when:

- equivalence requires arbitrary external/domain relevance not present in `F`;
- the problem becomes general semantic/text equivalence;
- identical model behavior becomes necessary to define the relation;
- full Accountability Graph/evidence theory becomes the primary problem;
- full Memory/summarization theory becomes necessary;
- Rich Effect, Boundary Reconfiguration or Multi-Agent semantics become the primary unresolved problem;
- current implementation lacks an information-positive dogfood surface;
- evidence supports only a directional sufficiency criterion, not a general equivalence theorem.

## 11. Engineering non-authority rule

WorkingSet, WorkingView, caller ingress, Tool observations, promotion, recall, source generations and current projection digests are dogfood surfaces only. The research criterion must be restatable as operational validity, obligation preservation, provenance/currentness/lifetime standing and bounded substitution.

## 12. Immediate next step

Commit/pin this Charter before analysis. Then run Round 1 over T1–T18 without modifying current engineering.
