# 132 — OPERATIONAL CLAIM STANDING MINIMAL MATERIALIZATION v1
# Acceptance + Falsification Contract

**Task:** `task:harness-operational-claim-standing-minimal-materialization-v1-20260819`  
**Authority:** Reference Contract 129 + Tournament 131.  
**Must be committed before `src/` modification.**

## 1. Selected implementation surface

Exactly one new value-layer module may be added. It may expose only:

1. `OperationalClaimRef`;
2. `OperationalClaimEvidenceRole`;
3. `OperationalClaimStandingView`;
4. `project_operational_claim_standing_view(...)`;
5. standing/role string constants if useful.

Public exports through `ordivon_harness.core` and `ordivon_harness.api` are permitted.

No persistence integration is selected.

## 2. `OperationalClaimRef` exact v1 shape

The first implementation is prebound to these responsibilities/fields:

- `claim_id: str` — exact bounded Q identity; must be non-empty/trimmed and start with `claim:`;
- `semantic_owner_ref: HarnessBoundReference` — exact semantic/truth-owner namespace/contract reference;
- `claim_contract_ref: HarnessBoundReference` — exact owner-grounded proposition/scope contract reference;
- `generation: int` — positive currentness generation.

Required behavior:

- immutable/frozen;
- canonical `to_dict` / `from_dict`;
- canonical `digest` property;
- subject identity is absent from ClaimRef;
- no truth/status/evidence fields.

No claim registry/discovery semantics are allowed.

## 3. `OperationalClaimEvidenceRole` exact v1 shape

Fields:

- `reference: HarnessBoundReference`;
- `role: str` in exactly:
  - `supporting`;
  - `counterevidence`;
  - `required_unknown`.

The role is an already-classified local evidential-use role. Harness v1 does **not** infer domain evidential bearing from evidence content.

Required behavior:

- immutable/frozen;
- canonical round-trip;
- a StandingView must reject duplicate exact refs or the same ref assigned to multiple roles.

## 4. `OperationalClaimStandingView` exact v1 shape

Fields:

- `claim: OperationalClaimRef`;
- `subject_ref: str` — exact local operational subject/consumer reference, non-empty/trimmed;
- `use_contract_ref: HarnessBoundReference`;
- `evidence_roles: tuple[OperationalClaimEvidenceRole, ...]`;
- `standing: str` in exactly:
  - `SUPPORTED`;
  - `CONTRADICTED`;
  - `CONFLICTED`;
  - `UNDERDETERMINED`;
- `generation: int` — positive immutable StandingView projection generation.

Required behavior:

- immutable/frozen;
- canonical round-trip + digest;
- standing must equal the pure projection rule in §5;
- no mutation of ClaimRef or other views;
- no registry/store/current-global-pointer semantics.

The v1 value contains enough basis to reconstruct claim/use/evidence/standing directly; therefore no separate `basis_digest` field is required. The view's canonical digest is the exact basis binding.

## 5. Pure standing projection rule

`project_operational_claim_standing_view(...)` consumes only already-admitted typed evidence roles.

Prebound rule:

1. if at least one `required_unknown` exists → `UNDERDETERMINED`;
2. else if both supporting and counterevidence exist → `CONFLICTED`;
3. else if supporting exists → `SUPPORTED`;
4. else if counterevidence exists → `CONTRADICTED`;
5. else → `UNDERDETERMINED`.

This is **evidence-role projection**, not truth evaluation.

A constructor/deserializer that supplies a standing inconsistent with the same evidence-role rule must fail closed.

## 6. Why `OperationalClaimUseDisposition` is excluded

E5-v2 tests evidence standing, not downstream settlement/continuation.

If implementation requires UseDisposition merely to materialize ClaimRef/StandingView, classify:

`IMPLEMENTATION_SCOPE_EXPANSION_REQUIRED`.

Do not implement it in v1.

## 7. Required unit/contract tests

### U1 — ClaimRef canonical round-trip/digest stability

### U2 — ClaimRef rejects invalid claim id / owner ref / contract ref / generation

### U3 — EvidenceRole canonical round-trip and exact role validation

### U4 — StandingView canonical round-trip/digest stability

### U5 — duplicate/cross-role evidence ref rejection

### U6 — projection: empty → UNDERDETERMINED

### U7 — supporting only → SUPPORTED

### U8 — counter only → CONTRADICTED

### U9 — support + counter → CONFLICTED

### U10 — required unknown dominates → UNDERDETERMINED

### U11 — supplied inconsistent standing fails closed

### U12 — ClaimRef has no subject/status/evidence/global-registry field

### U13 — current public API exports exact new value-layer symbols

## 8. Prebound E5-v2 direct dogfood

After implementation/tests are committed and pinned, run a separate research experiment using only the public API.

### E5v2-1 — one exact Q

Create one ClaimRef Q and use the exact same object/value for A and B.

### E5v2-2 — A supported

A admits EA as `supporting`; project generation 1 → `SUPPORTED`.

### E5v2-3 — B underdetermined

B generation 1 has no admitted EA → `UNDERDETERMINED`.

### E5v2-4 — visibility without adoption

Fixture may make EA visible to B externally, but must call the projection with unchanged B admitted evidence basis. B view must remain byte/digest identical to its prior generation-1 view.

Fixture visibility is not Harness admission.

### E5v2-5 — explicit B admission

B explicitly includes the exact EA reference as `supporting` and projects generation 2 → `SUPPORTED`.

### E5v2-6 — unchanged Q/A/history

After B generation 2:

- Q digest unchanged;
- A view digest unchanged;
- old B generation-1 view remains unchanged/valid;
- new B view has a different digest/generation;
- no registry/store is used.

## 9. Direct falsifiers

Classify `E5V2_DIRECT_FALSIFIER_FOUND` if the admitted implementation requires or exhibits any of:

- Q duplication per subject;
- global mutable standing attached to Q;
- evidence visibility automatically changes B standing without explicit admitted roles;
- B adoption mutates A view;
- B generation 2 rewrites/invalidates old B generation 1 value;
- owner/scope/currentness cannot be exact-bound;
- public materialization requires registry/store/truth lookup.

## 10. Materialization admission criteria

`MATERIALIZATION_ADMITTED` requires:

- U1–U13 pass;
- full repository tests relevant to public/core contract compatibility pass;
- no existing persistence migration;
- changed production paths limited to new value module + public/core export wiring;
- E5-v2 produces no direct falsifier;
- no scope-expansion mechanism is added.

## 11. Allowed final classifications

- `MATERIALIZATION_ADMITTED`;
- `MATERIALIZATION_FALSIFIER_FOUND`;
- `REFERENCE_CONTRACT_TOO_STRONG`;
- `IMPLEMENTATION_SCOPE_EXPANSION_REQUIRED`;
- combined with `E5V2_DIRECT_SUPPORT_IN_SCOPE` or `E5V2_DIRECT_FALSIFIER_FOUND`.

## 12. Foundation/theory guard

No implementation result creates HaF62 or Campaign 7. Any semantic contradiction is routed back as explicit theory/research reopen pressure rather than silently redefining Reference Contract 129 in code.
