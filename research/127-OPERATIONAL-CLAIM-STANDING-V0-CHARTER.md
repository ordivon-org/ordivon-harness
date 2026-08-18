# 127 — OPERATIONAL CLAIM STANDING ENGINEERING CONSUMPTION v0
# Research Charter — Realization Claim / Evidence Standing / Subject View Minimal Contract

**Control task:** `task:harness-operational-claim-standing-engineering-consumption-v0-20260819`  
**Research role:** engineering-consumption research over Campaign-3 + FOR semantics.  
**Production implementation:** forbidden during this branch.  
**Foundation effect:** none unless an explicit later audit finds otherwise.

## 1. Research question

Does Harness need a generic minimal engineering-consumption contract for bounded operational claims and subject/use-relative evidence standing, and if so what is the thinnest contract that enables direct falsification without turning Harness into a global truth/claim authority?

## 2. Mandatory separation

The branch prebinds three semantically distinct layers:

1. **Claim meaning / truth authority** — defined and owned externally by the relevant Runtime/domain/Network/Normative/other semantic owner.
2. **Claim identity/reference** — a stable, exact reference sufficient for Harness to know which bounded proposition/evaluation target is being discussed.
3. **Subject/use-relative standing projection** — Harness-side operational projection of admissible evidence standing for one subject/use contract at one currentness boundary.

The branch fails if a viable engineering contract requires these three layers to collapse.

## 3. Candidate minimal grammar

This is a hypothesis, not an admitted schema.

### 3.1 `OperationalClaimRef`

Potential technology-neutral responsibilities:

- exact claim reference identity;
- claim-kind/type reference if owner exposes one;
- semantic owner / authority namespace reference;
- owner-grounded claim contract/content digest;
- scope reference(s);
- generation/version/epoch/currentness discriminator where required;
- optional issuer/evidence-authority reference when issuer differs from semantic owner.

Explicitly excluded:

- mutable truth value;
- Harness-authored physical/domain semantics;
- subject-local evidence standing;
- global settlement/completion state.

### 3.2 `OperationalClaimStandingView`

Potential technology-neutral responsibilities:

- exact `OperationalClaimRef`;
- operational subject / local consumer identity;
- use-contract identity/digest;
- evidence refs actually admitted for this view;
- supporting/counter/support-unknown dependency roles as needed;
- one evidence-relative standing among:
  - `SUPPORTED`;
  - `CONTRADICTED`;
  - `CONFLICTED`;
  - `UNDERDETERMINED`;
- currentness / projection generation;
- provenance/basis digest;
- optional separate settlement/use disposition.

Standing is a projection, not a mutable field on the claim.

### 3.3 Settlement / continuation relation

If required, this is separate from evidence standing. Possible use-relative dispositions:

- `SETTLED_FOR_USE`;
- `RECONCILIATION_REQUIRED`;
- `INSUFFICIENT_EVIDENCE`;
- `EXTERNAL_DECISION_REQUIRED`.

No universal retry permission or global causal finality is implied.

## 4. Rivals

### R1 — Global Mutable EffectStatus
One claim/effect object carries a single mutable global status.

### R2 — Harness Claim Object Owns Truth
The generic claim object stores authoritative world/domain truth directly.

### R3 — Standing Is Global Property of Q
All subjects share one current standing field attached to the claim.

### R4 — Receipt Equals Standing
Any terminal/evidence receipt directly constitutes the full claim standing.

### R5 — Per-Agent Claim Copies
Each subject creates/forks a separate claim Q when its evidence differs.

### R6 — Global Harness Claim Registry
Harness stores and resolves all claims centrally as mutable authority.

### R7 — Owner-Specific Opaque Claims Only
No generic Harness claim grammar exists; each owner exposes unrelated claim/evidence contracts and Harness treats them as opaque evidence only.

### R8 — Production Schema Directly From Research Prose
Campaign-3 relation names are converted immediately into classes/tables/enums without consumption analysis.

### R9 — Evidence Standing Without Use Contract
One evidence-standing projection is assumed valid for all downstream uses.

### R10 — Settlement Equals Truth/Completion
`SETTLED_FOR_USE` is treated as global truth, external causal finality, domain success, or Host completion.

## 5. Required destructive cases

### T1 — same Q, A supported, B underdetermined
Must be representable without forking Q or global standing mutation.

### T2 — B adopts A evidence later
B standing may change while A standing and Q identity remain unchanged.

### T3 — same evidence supports narrow Q but not broader Q'
Receipt/evidence scope must not expand automatically.

### T4 — owner claim generation changes
Old claim/currentness cannot silently remain current.

### T5 — two authoritative evidence issuers conflict
Standing may become conflicted without forcing Harness to decide world truth.

### T6 — evidence visible but not admitted
Visibility does not change standing.

### T7 — evidence provenance valid but evidential bearing absent
Valid provenance alone does not support Q.

### T8 — settled for one use, unresolved for another
Settlement must be use-relative.

### T9 — compensation produces later claim edge
Prior supported effect claim remains historical.

### T10 — Host task remains open after Q settled
Claim settlement must not imply Host completion.

### T11 — Runtime receipt settles Runtime-owned narrow Q but not domain goal Q'
Owner authority remains scoped.

### T12 — Network delivery evidence cannot settle remote semantic-effect claim
Network truth boundary remains intact.

### T13 — claim meaning is owner-specific but shared exact identity is needed across subjects
Tests whether a thin generic ref helps without generic truth semantics.

### T14 — no central registry exists
Two subjects can exchange/adopt exact claim refs/views through explicit references without Harness owning a global mutable claim database.

## 6. Evaluation dimensions

A viable engineering-consumption form must satisfy:

- **owner preservation** — truth/meaning authority remains external;
- **subject locality** — evidence standing may differ by subject/use;
- **stable identity** — same Q remains identifiable across evidence transfer;
- **currentness** — generation/version/scope changes are explicit;
- **history preservation** — updated standing does not rewrite prior standing/evidence;
- **minimality** — no registry/workflow/database semantics unless deletion-essential;
- **interoperability** — enough common grammar for cross-subject and cross-owner mediation;
- **dogfoodability** — enables direct E5-style falsification;
- **non-scalarization** — no universal success/effect scalar.

## 7. Outcome classes

Possible closeout classes:

- `GENERIC_MINIMAL_CONTRACT_ADMITTED`;
- `PROJECTION_ONLY_NO_REGISTRY`;
- `OWNER_SPECIFIC_ONLY`;
- `MATERIALIZATION_DEFERRED`;
- `THEORY_REOPEN_REQUIRED`.

Multiple compatible labels may be used, e.g. a generic minimal reference/projection contract may be admitted **and** explicitly require `PROJECTION_ONLY_NO_REGISTRY`.

## 8. Non-goals

This branch does not:

- implement production classes/tables;
- create a global claim service;
- define Runtime/domain/Network/Normative truth semantics;
- define universal retry/idempotency policy;
- define Host completion;
- create Campaign 7;
- create HaF62.

## 9. Stop rule

Commit/pin this Charter before destructive analysis. If a generic contract survives, derive only a technology-neutral reference contract and engineering-consumption admission boundary. Production materialization requires a later explicit implementation/admission task.
