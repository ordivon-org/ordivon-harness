# 129 — OPERATIONAL CLAIM STANDING v0
# Technology-Neutral Engineering-Consumption Reference Contract

**Authority:** derived from Charter `127` and destructive analysis `128`.  
**Standing:** admitted research-level engineering-consumption contract.  
**Not:** production schema, registry design, database model, RPC protocol or new Foundation.

## 1. Contract purpose

Provide the minimum interoperable grammar needed for Harness to mediate evidence-relative standing about one exact externally owned bounded claim across Runs/subjects/uses without acquiring truth ownership.

## 2. Contract A — `OperationalClaimRef`

An implementation MUST be able to carry an exact reference with the following semantic responsibilities:

### A1 — claim identity

One stable identity for one bounded proposition/evaluation target Q.

### A2 — semantic owner binding

An exact reference to the owner/authority that defines Q's meaning and truth scope.

Harness MUST NOT reinterpret this as Harness truth ownership.

### A3 — claim-contract/scope binding

An exact digest-bound owner reference that fixes the bounded proposition and scope being evaluated.

A claim reference without sufficient scope binding is not adequate for standing evaluation.

### A4 — currentness binding

Generation/version/epoch/currentness must be explicit whenever the owner claim contract can change.

Old generations remain historical; they do not silently become current.

### A5 — subject independence

Subject/Agent identity MUST NOT be part of Q's semantic identity merely because different subjects hold different evidence.

One Q may be referenced by many subjects.

## 3. Contract B — `OperationalClaimStandingView`

An implementation MUST be able to materialize/reconstruct a local immutable projection with the following responsibilities:

### B1 — exact claim binding

Bind one exact `OperationalClaimRef`.

### B2 — local consumer/subject binding

Bind the operational subject/consumer for whom this evidence standing is being projected.

### B3 — use-contract binding

Bind the exact downstream use/evaluation contract under which the standing is meaningful.

A standing view without a use contract MUST NOT be assumed universally adequate.

### B4 — admitted evidence basis

Bind the exact evidence references actually admitted into this projection.

Visibility/discoverability alone is insufficient.

### B5 — evidential roles

Preserve enough typed role information to distinguish at minimum:

- supporting evidence;
- counterevidence;
- required/remaining unknowns where the use contract requires them.

Dependency/common-cause information may be consumed from OCSS/accountability surfaces where required rather than duplicated.

### B6 — evidence-relative standing

One of:

- `SUPPORTED`;
- `CONTRADICTED`;
- `CONFLICTED`;
- `UNDERDETERMINED`.

These values describe the projection's admissible evidence standing, not external truth itself.

### B7 — projection currentness

Carry a projection generation/currentness discriminator.

A later view may supersede an earlier current view without deleting the earlier historical view.

### B8 — provenance/basis

Provide an exact digest/provenance binding sufficient to reconstruct which claim, use contract and admitted evidence produced the view.

## 4. Contract C — optional `OperationalClaimUseDisposition`

Where continuation/settlement semantics are needed, an implementation MAY expose a separate use-relative disposition that binds exact claim/view/use references.

Permitted technology-neutral roles include:

- `SETTLED_FOR_USE`;
- `RECONCILIATION_REQUIRED`;
- `INSUFFICIENT_EVIDENCE`;
- `EXTERNAL_DECISION_REQUIRED`.

This disposition MUST remain separate from:

- external truth;
- physical causal finality;
- semantic/domain success;
- universal retry permission;
- Host Task completion.

## 5. Required invariants

### I1 — Same Q, different local standings

`Standing_A(Q)` and `Standing_B(Q)` may differ without Q duplication or inconsistency.

### I2 — Evidence adoption updates a view, not Q

When B adopts new evidence, B may produce a new StandingView generation. Q identity and A's view do not change.

### I3 — Receipt is an evidence input

A receipt MUST NOT automatically become a StandingView.

### I4 — Scope cannot expand silently

Evidence bearing on Q does not automatically bear on broader/different Q'.

### I5 — Claim currentness is explicit

A changed owner claim contract/generation requires explicit currentness/readmission handling.

### I6 — History is preserved

New standing/currentness does not rewrite prior evidence, prior claim generations or prior StandingViews.

### I7 — No required global mutable registry

Interoperability MUST be possible through exact owner-grounded references and local projections without one semantic-authority global claim database.

### I8 — Owner truth remains external

Harness may carry claim identity, evidence and standing projection but MUST NOT become the authoritative resolver of Runtime/domain/Network/Normative/World truth.

## 6. Existing surface reuse

Future implementation SHOULD prefer composition over duplication:

- exact reference/digest patterns from `HarnessBoundReference`;
- Run/Runtime receipts as evidence inputs;
- WorkingSet/WorkingView admission/currentness patterns;
- OCSS evidence/dependency/accountability structures;
- existing lineage/history semantics;
- CompletionProposal remains separate from claim settlement.

This contract does not authorize a second evidence store, second history store or second authority plane.

## 7. Direct dogfood enabled

A future implementation can now prebind a clean E5-v2 fixture:

1. owner fixture provides one exact Q/ClaimRef;
2. Subject A admits evidence EA and projects `SUPPORTED`;
3. Subject B initially lacks EA and projects `UNDERDETERMINED`;
4. both views bind the same Q identity;
5. A-origin evidence becomes visible to B but B view remains unchanged;
6. B explicitly adopts EA;
7. B creates a new StandingView generation, potentially `SUPPORTED`;
8. Q identity and A view remain unchanged;
9. no global mutable claim registry is consulted.

This future fixture can directly falsify the contract if a production materialization cannot preserve these invariants.

## 8. Explicitly non-admitted

Not admitted by v0:

- exact field names;
- exact serialization;
- Python classes;
- SQL schema/tables;
- claim discovery service;
- global claim registry;
- automatic claim evaluation engine;
- automatic owner adapters;
- universal claim taxonomy;
- normative responsibility/blame semantics;
- domain truth semantics.

## 9. Admission statement

Admitted responsibility boundary:

> Harness may generically reference an exact owner-defined bounded operational claim and materialize subject/use/evidence-relative standing projections about that claim. The claim's meaning and truth remain owner-defined; standing remains projection-local; history/currentness remain explicit; no global Harness claim registry is required.
