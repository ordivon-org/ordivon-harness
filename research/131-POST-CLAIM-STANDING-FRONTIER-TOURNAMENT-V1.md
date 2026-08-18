# 131 — POST-CLAIM-STANDING FRONTIER TOURNAMENT v1

**Control task:** `task:harness-post-claim-standing-frontier-tournament-20260819`  
**Starting authority:** Operational Claim Standing v0 closeout at `37a57e608a16c7624c262cb535940afa3519b72c`.  
**Foundation effect:** none. HaF0–HaF61 remain frozen; HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 1. Decision question

After the technology-neutral Claim Standing reference contract has been admitted, should Harness next:

1. minimally materialize that contract and immediately run E5-v2 direct dogfood;
2. pursue direct Agent→Agent delegation/revocation;
3. pursue federation partition/branch/reconciliation;
4. return to Campaign-3 rich-effect dogfood;
5. return to Campaign-4 accountability independence/rebuttal dogfood;
6. return to Campaign-5 provider/locus OPUR dogfood;
7. pursue cross-implementation invariance;
8. open Campaign 7 theory.

No scalar score is used.

## 2. New feasibility fact

Current production code already contains the implementation patterns needed for a **small value-layer materialization**:

- immutable digest-bound `HarnessBoundReference`;
- immutable canonical `HarnessStrategyEvidence` with exact content/reference digest checking;
- `to_dict` / `from_dict` canonical contracts;
- public API re-export patterns;
- no database is required for a value object to be a valid public engineering-consumption surface.

Therefore Claim Standing v0 does not require a new registry, store, service or workflow before E5-v2 becomes directly testable.

## 3. Candidate C1 — Minimal Claim Standing materialization + E5-v2

**Information value:** highest current closed-loop value.

This branch would complete the sequence:

`Campaign-3/FOR theory → E5 gap → reference contract → minimal implementation → direct falsification`.

The implementation can be tightly bounded to:

- one exact `OperationalClaimRef` value type;
- one immutable `OperationalClaimStandingView` value type;
- one pure standing-projection constructor/function over already-classified evidence roles;
- public API exports;
- exact round-trip and invalid-input tests;
- E5-v2 two-subject dogfood.

The optional `OperationalClaimUseDisposition` is **not required** to test E5-v2 and should remain unimplemented unless the acceptance contract proves it deletion-essential.

No SQLite table, global registry, discovery service, evidence store or mutable status object is needed.

Decision: **SELECTED.**

## 4. Candidate C2 — Agent→Agent delegation/revocation

Still blocked by lack of a first-class Agent→Agent delegation lifecycle. Current `HarnessExecutionMandate` is strong caller→Run authority evidence but does not itself instantiate federation delegation.

Decision: defer. Do not manufacture a relation merely to test it.

## 5. Candidate C3 — federation partition/branch/reconciliation

Still lacks a first-class cross-subject branch relation. Existing WorkingSet successors and recovery are adjacent single-Run semantics.

Decision: defer.

## 6. Candidate C4 — Campaign-3 rich-effect dogfood

High value, but requires richer external-owner effect evidence. The Claim Standing branch now has a concrete, low-cost direct falsification opportunity and should be closed first.

Decision: defer.

## 7. Candidate C5 — Campaign-4 accountability dogfood

Important but already has a usable OCSS materialization surface. E5-v2 closes a newer explicit implementation gap.

Decision: defer.

## 8. Candidate C6 — Campaign-5 OPUR dogfood

Important but externally dependent and does not complete the current research→engineering loop.

Decision: defer.

## 9. Candidate C7 — cross-implementation invariance

Standing programme; independent implementation diversity remains insufficient.

Decision: defer.

## 10. Candidate C8 — Campaign 7 theory

No new theory contradiction dominates current materialization/falsification work.

Decision: not selected.

## 11. Tournament result

**SELECTED NEXT WORK — MINIMAL IMPLEMENTATION + DIRECT DOGFOOD, NOT NEW THEORY:**

# Operational Claim Standing Minimal Materialization v1
## + E5-v2 Shared-Q / Subject-Local Standing Direct Dogfood

This is an engineering-consumption implementation/admission branch with an embedded direct falsification stage.

## 12. Implementation scope ceiling

The branch may implement only what is required to make Reference Contract 129 directly testable:

### Required

- exact owner-grounded claim identity/scope/currentness value representation;
- exact subject/use/evidence-relative immutable StandingView representation;
- evidence-role representation sufficient for support/counter/required-unknown distinctions;
- evidence-relative standing projection;
- canonical digest and round-trip behavior;
- public API exposure;
- direct E5-v2 dogfood.

### Explicitly not selected

- global Claim registry;
- SQLite claim tables;
- claim discovery;
- claim workflow;
- automatic owner truth lookup;
- domain-specific claim semantics;
- global mutable status;
- `OperationalClaimUseDisposition` unless direct implementation pressure proves it required;
- delegation/partition features.

## 13. Prebound E5-v2 target

The implementation branch must eventually demonstrate or falsify:

1. one exact owner-grounded Q;
2. A and B bind the same Q identity;
3. A StandingView is `SUPPORTED` using admitted EA;
4. B StandingView is `UNDERDETERMINED` without EA;
5. A-origin EA becomes visible to B but B standing does not change merely from visibility;
6. B explicitly admits EA;
7. B creates a later StandingView generation that may become `SUPPORTED`;
8. Q identity and A StandingView remain unchanged;
9. prior B StandingView remains a valid historical immutable object;
10. no global registry/storage is consulted.

## 14. Failure classes

The implementation branch must distinguish:

- `MATERIALIZATION_ADMITTED`;
- `MATERIALIZATION_FALSIFIER_FOUND`;
- `REFERENCE_CONTRACT_TOO_STRONG`;
- `IMPLEMENTATION_SCOPE_EXPANSION_REQUIRED`;
- `E5V2_DIRECT_SUPPORT_IN_SCOPE`;
- `E5V2_DIRECT_FALSIFIER_FOUND`.

Any need for database/global registry/owner truth inference to satisfy E5-v2 is pressure against the current minimal contract, not permission to add those mechanisms automatically.

## 15. Selection standing

- `SelectedHarnessImplementationBranch = Operational Claim Standing Minimal Materialization v1 + E5-v2`.
- `NextHarnessResearchCampaign = UNKNOWN`.
- `NextHarnessFoundationRoute = UNKNOWN`.
- HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.
