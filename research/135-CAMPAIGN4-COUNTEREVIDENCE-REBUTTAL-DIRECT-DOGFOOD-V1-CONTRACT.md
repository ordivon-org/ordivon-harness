# 135 — CAMPAIGN-4 COUNTEREVIDENCE / REBUTTAL DIRECT DOGFOOD v1
# Prebound Experiment Contract

**Task:** `task:harness-campaign4-counterevidence-rebuttal-direct-dogfood-v1-20260819`  
**Selection authority:** Tournament 134.  
**Historical Campaign-4 authority:** closeout 110.  
**Product falsification target:** current public Claim Standing v1 at branch base `77dad68e792c9644e3700b7da4f077d929274a7f`.

## 1. Scope

This branch tests one previously conceptual-only Campaign-4 frontier: **counterevidence/rebuttal revision**.

It does not test causal/common-cause independence, support cycles, cross-owner support composition, normative blame, or claim truth.

No production `src/` modification is authorized.

## 2. Required public surface

Fixture Harness semantics must be imported only from `ordivon_harness.api`:

- `HarnessBoundReference`;
- `OperationalClaimRef`;
- `OperationalClaimEvidenceRole`;
- `OperationalClaimStandingView`;
- `project_operational_claim_standing_view`.

No private module, SQLite store, registry or persistence surface may be used.

## 3. RBD1 — Initial support

One exact owner-grounded Q; Subject A / use U admits exact support evidence ES.

Expected A1:

`SUPPORTED`.

## 4. RBD2 — Counterevidence visibility without admission

Exact counterevidence EC becomes fixture-visible/addressable to A, but A's admitted evidence-role tuple remains unchanged.

Expected:

- A1 re-projection is byte/digest identical;
- standing remains `SUPPORTED`.

Visibility is fixture-owned and must not be called Harness evidence admission.

## 5. RBD3 — Explicit rebuttal admission

A later A generation explicitly admits exact EC as `counterevidence` while retaining exact ES as `supporting`.

Expected A2:

`CONFLICTED`.

No prior support deletion is allowed.

## 6. RBD4 — History preservation

After A2:

- Q digest unchanged;
- A1 digest unchanged;
- exact ES/EC refs unchanged;
- A2 generation > A1 generation;
- A2 digest differs from A1;
- A1 remains valid immutable history.

## 7. RBD5 — Counterevidence-only local view

Subject B / same use U binds the same Q but admits only exact EC as `counterevidence`.

Expected B1:

`CONTRADICTED`.

This is local evidence standing, not external truth.

## 8. RBD6 — Required unknown remains first-class

Subject C / same Q/U admits exact ES as `supporting` plus exact RU as `required_unknown`.

Expected C1:

`UNDERDETERMINED`.

Positive support must not erase a required unknown.

## 9. RBD7 — No global contest/truth state

Fixture must establish:

- Q has no mutable `standing`, `status`, `truth`, or `contested` field;
- no `OperationalClaimRegistry` public surface exists;
- no registry/store is consulted.

## 10. RBD8 — Same-ref role alias fails closed

Constructing one StandingView where the same exact evidence ref occupies both `supporting` and `counterevidence` roles must raise/fail closed.

## 11. Required machine classification

If all prebound cases pass:

`CAMPAIGN4_REBUTTAL_DIRECT_SUPPORT_IN_SCOPE`.

If any semantic assertion fails:

`REBUTTAL_DIRECT_FALSIFIER_FOUND`.

If the cases cannot be expressed using the selected public surface without production changes:

`CLAIM_STANDING_MATERIALIZATION_GAP_REOPENED`.

## 12. Interpretation guard

A successful run supports only bounded product semantics for:

- explicit counterevidence admission;
- local standing revision;
- support/counter coexistence as conflict;
- history preservation;
- required unknown preservation;
- role alias fail-closed.

It does **not** establish:

- whether ES or EC are actually true/correct in the external domain;
- causal independence of evidence sources;
- a complete OCSS/accountability engine;
- normative responsibility;
- cross-owner support composition.

## 13. Foundation/theory guard

No result creates Campaign 7 or HaF62. Any contradiction is an explicit reopen pressure on Claim Standing/Campaign-4 materialization, not permission to rewrite theory in the fixture.
