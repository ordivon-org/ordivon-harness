# 128 — OPERATIONAL CLAIM STANDING v0
# Destructive Analysis and Minimal Contract Derivation

**Prebinding authority:** Charter at commit `0cff467` before this analysis.  
**Analysis class:** engineering-consumption destructive reconstruction, not production design.

## 1. Analysis result

The generic-contract hypothesis survives only after a major narrowing.

Final candidate form:

`GENERIC_MINIMAL_CONTRACT_ADMITTED` + `PROJECTION_ONLY_NO_REGISTRY`.

What is generic is **reference/projection grammar**, not claim meaning, truth semantics or a central claim service.

## 2. Core decomposition

A viable engineering-consumption model requires three distinct objects/roles:

### A — Owner-grounded `OperationalClaimRef`

A thin exact identity for one bounded claim whose meaning remains external-owner defined.

Minimum responsibilities:

- stable `claimRef` identity;
- exact `semanticOwnerRef` / authority namespace;
- exact owner-grounded `claimContractRef` or equivalent digest-bound reference defining proposition + scope;
- explicit generation/version/currentness discriminator where the owner contract can change.

The generic Harness grammar need not understand the internal domain proposition. It only needs to bind which owner-defined bounded claim is being evaluated.

### B — Subject/use-relative `OperationalClaimStandingView`

A projection over one exact Q for one operational subject and one use contract.

Minimum responsibilities:

- exact `claimRef`;
- exact operational `subjectRef` / local consumer identity;
- exact `useContractRef` or digest;
- exact evidence refs admitted into this projection;
- evidence-role projection sufficient to distinguish supporting, counterevidence and required/remaining unknowns where relevant;
- evidence-relative standing:
  - `SUPPORTED`;
  - `CONTRADICTED`;
  - `CONFLICTED`;
  - `UNDERDETERMINED`;
- projection/currentness generation;
- basis/provenance digest sufficient to show which admitted evidence and use contract produced the view.

The standing view is immutable/history-preservable for its generation. A later view supersedes it for a current use; it does not mutate Q or rewrite the prior view.

### C — Optional use-relative `OperationalClaimUseDisposition`

Settlement/continuation is separate from evidential standing.

Possible technology-neutral dispositions:

- `SETTLED_FOR_USE`;
- `RECONCILIATION_REQUIRED`;
- `INSUFFICIENT_EVIDENCE`;
- `EXTERNAL_DECISION_REQUIRED`.

A disposition must bind:

- claim/claim-set identity;
- use contract;
- standing-view refs/digests used;
- currentness/projection generation.

It does not imply retry safety, domain success, Host completion or global causal finality.

## 3. Why standing cannot live on Q

T1 and FOR already require:

`Standing_A(Q) = SUPPORTED`  
`Standing_B(Q) = UNDERDETERMINED`.

A mutable `Q.status` cannot represent this without either:

- overwriting one subject's standing;
- hiding subject/use scope;
- or creating a map inside Q that turns the claim object into a federation state registry.

Therefore:

> standing is not a property of the claim; it is a subject/use/evidence-relative projection **about** the claim.

This is the decisive engineering-consumption correction.

## 4. Why Q must not be copied per Agent

R5 fails because `Q_A` / `Q_B` copies destroy the ability to state that A and B disagree or differ in evidence **about the same bounded proposition**.

The correct structure is:

`one owner-grounded Q identity`  
`many local standing views`.

This permits later evidence adoption or reconciliation without claim-identity rewriting.

## 5. Why a thin generic ClaimRef is still useful

R7 (`OWNER_SPECIFIC_ONLY`) is partially attractive because claim meaning is owner-specific.

But a total absence of generic claim identity causes concrete interoperability failures:

- two Harness subjects cannot prove they are discussing the same Q without owner-specific pairwise adapters;
- evidence-transfer surfaces cannot bind evidence to the exact common claim generically;
- standing-view provenance cannot remain technology-neutral across Runtime/domain owners;
- E5 direct federation dogfood remains impossible except via fixture metadata.

Therefore a **thin generic reference grammar** is justified even though claim semantics remain owner-specific.

The generic layer says:

> “this exact owner-defined bounded claim Q”

not:

> “Harness understands/owns what Q means in the world.”

## 6. Why no global Claim registry is needed

R6 fails deletion-essentiality.

T14 can be satisfied with exact references plus owner resolution/adoption. Cross-subject exchange requires:

- stable Q reference;
- exact evidence refs;
- local standing projection.

It does not require:

- a globally mutable claim row;
- centralized current status;
- universal claim discovery;
- Harness-owned truth resolution.

A registry might later exist as an Atlas/observability projection, but it must not become semantic authority.

Hence:

`PROJECTION_ONLY_NO_REGISTRY`.

## 7. Receipt is evidence, not standing

R4 fails.

A receipt may:

- support a narrow issuer-owned Q;
- fail to bear on broader Q';
- conflict with other admissible evidence;
- be visible but not admitted;
- be stale for the current claim generation.

Therefore:

`Receipt != Claim Standing`.

Existing Run Receipt / Runtime evidence should remain evidence inputs rather than be renamed into claim status objects.

## 8. Destructive cases

### T1 — same Q, A supported, B underdetermined

PASS with one ClaimRef + two StandingViews. Global Q.status fails.

### T2 — B adopts A evidence later

PASS: create a later B StandingView generation with newly admitted evidence. A view and Q identity remain unchanged.

### T3 — narrow Q vs broader Q'

PASS only if claim contract/scope identity is exact. One receipt cannot expand from Q to Q' without owner-grounded claim/evidential-bearing relation.

### T4 — owner claim generation changes

PASS only if ClaimRef/currentness binds generation/version. Old standing remains historical; new current Q generation requires a new projection/readmission.

### T5 — authoritative issuers conflict

PASS: StandingView may become `CONFLICTED`; Harness does not decide world truth merely because evidence conflicts.

### T6 — evidence visible but not admitted

PASS: visible evidence is absent from admitted evidence refs/basis; standing need not change.

### T7 — provenance valid, bearing absent

PASS: provenance validity alone does not make evidence supporting. Evidence-role/evidential-bearing projection remains distinct.

### T8 — settled for one use, unresolved for another

PASS only when UseDisposition binds an explicit use contract. Global settlement fails.

### T9 — compensation later edge

PASS: later Q_compensation / evidence does not mutate or erase prior Q_effect StandingViews/history.

### T10 — Host task open after Q settled

PASS because Host completion is external to ClaimUseDisposition.

### T11 — Runtime narrow Q settled, domain Q' unresolved

PASS because semantic owner/claim contract scope remains exact.

### T12 — Network delivery evidence vs remote semantic effect

PASS because Network-owned delivery Q and domain/remote-effect Q are distinct owner/scope claims.

### T13 — owner-specific meaning + shared exact identity

PASS with opaque owner-grounded ClaimRef. Generic semantics beyond identity are unnecessary.

### T14 — no central registry

PASS: exact refs and immutable subject/use projections are sufficient for exchange/adoption/reconstruction. Registry is not deletion-essential.

## 9. Rival standing

| Rival | Standing |
|---|---|
| R1 Global Mutable EffectStatus | REJECTED |
| R2 Harness Claim Object Owns Truth | REJECTED |
| R3 Standing Is Global Property of Q | REJECTED |
| R4 Receipt Equals Standing | REJECTED |
| R5 Per-Agent Claim Copies | REJECTED |
| R6 Global Harness Claim Registry | REJECTED |
| R7 Owner-Specific Opaque Claims Only | REVISED — owner-specific meaning retained, thin generic ref admitted |
| R8 Production Schema Directly From Prose | REJECTED |
| R9 Standing Without Use Contract | REJECTED |
| R10 Settlement Equals Truth/Completion | REJECTED |

## 10. Minimum interoperable contract

The research does **not** admit exact field names/classes, but it admits this technology-neutral responsibility boundary:

```text
Owner Claim Contract
    ↓ exact owner-grounded binding
OperationalClaimRef Q
    ├─ claim identity
    ├─ semantic owner
    ├─ claim contract/scope binding
    └─ generation/currentness

Evidence E1..En
    ↓ local admission + evidential-bearing roles

OperationalClaimStandingView(S, U, Q)
    ├─ subject S
    ├─ use contract U
    ├─ admitted evidence refs/roles
    ├─ SUPPORTED | CONTRADICTED | CONFLICTED | UNDERDETERMINED
    ├─ projection generation
    └─ provenance/basis

optional:
OperationalClaimUseDisposition(U, Q/Q-set)
    └─ SETTLED_FOR_USE | RECONCILIATION_REQUIRED |
       INSUFFICIENT_EVIDENCE | EXTERNAL_DECISION_REQUIRED
```

## 11. Reuse vs new engineering surface

Existing engineering surfaces can be consumed rather than duplicated:

- `HarnessBoundReference` pattern can inform exact refs;
- Runtime/Run Receipts remain evidence refs;
- WorkingSet/WorkingView admission semantics inform local evidence admission/currentness;
- OCSS informs evidence role/dependency/accountability semantics;
- CompletionProposal remains separate from claim settlement.

The new consumption boundary, if later implemented, should therefore be **thin**: claim reference + standing projection + optional use disposition, not a new evidence store or workflow engine.

## 12. Foundation/theory pressure

`NO_FOUNDATION_PRESSURE`.

`THEORY_REOPEN_REQUIRED = false`.

The gap was engineering consumption: Campaign-3/FOR semantics were sufficient to derive a minimal materialization boundary without new owner-native primitive discovery.

## 13. Analysis standing

Admit for closeout review:

- `GENERIC_MINIMAL_CONTRACT_ADMITTED`;
- `PROJECTION_ONLY_NO_REGISTRY`.

Still not authorized:

- exact Python classes;
- exact JSON schema;
- SQLite tables;
- global registry/service;
- automatic owner claim discovery;
- universal claim evaluation engine.
