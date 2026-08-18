# 149 — POST-EVIDENCE-REPAIR TYPED FRONTIER TOURNAMENT v1

**Starting authority:** Evidence Index Typed Ingestion & Currentness Repair v1 closeout at canonical `df5195efc84299ebed868bd41fe2c86bff0cc9c8`.  
**Control continuity:** `task:harness-next-conversation-handoff-20260819` revision 8 at tournament start.  
**Foundation effect:** none. HaF0–HaF61 remain frozen; HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 1. Decision question

After evidence currentness repair 147/148 is complete, which remaining Harness frontier now has the strongest direct information-positive value without inventing missing semantics?

Candidates:

1. Campaign-4 dependency/common-cause independence;
2. Campaign-5 full directional provider transition;
3. Campaign-5 locus migration;
4. Campaign-5 internalization/externalization;
5. `OperationalClaimUseDisposition`;
6. Agent→Agent delegation/revocation;
7. federation partition/branch/reconciliation;
8. cross-implementation invariance;
9. wheel/public-API release-contract currentness;
10. any other newly exposed current production/release pressure.

No scalar score is used. Dimensions remain separate: direct expressibility, destructive testability, information gain, architecture-falsification power, owner-boundary cleanliness, fixture semantic invention, real current surface and engineering leverage.

## 2. Revalidated starting state

Canonical local Harness main:

`df5195efc84299ebed868bd41fe2c86bff0cc9c8`.

Current accepted state:

- deterministic suite: 450 tests OK, 3 skipped;
- evidence contract: valid, 70 historical / 1 verified;
- documentation contract: valid;
- dependency contract: valid;
- current no-Tool repair accepted;
- Claim Standing remains a current public product surface;
- no production source changes occurred in Evidence repair 147/148.

## 3. Fresh external-owner locus check

Fresh Workstation observations still show:

### `surf-clash`

- `UNAVAILABLE`;
- same generation digest `sha256:d7e66dcb53f484bb87bcd7649231d5f205b01dafd49a2f4f9e89be910732e92c`;
- namespace absent;
- resolver/transport/service unhealthy.

### `finance-okx`

- `UNKNOWN`;
- listener unreachable;
- no eligible/active member.

No owner-grounded before→after locus transition pair exists.

## 4. C1 — Campaign-4 dependency / independence

No first-class generic dependency/common-cause relation exists. Artifact/Agent multiplicity cannot establish causal independence.

**Disposition:** `DEFER / RELATION-BLOCKED`.

## 5. C2 — full directional provider OPUR

ProviderUsePolicy directly proves endpoint route admission under U, but current product still lacks a first-class transition T. Historical H5 remains historical.

**Disposition:** `DEFER / TRANSITION-RELATION-BLOCKED`.

## 6. C3 — locus migration

Current owner facts are negative state only, not migration evidence.

**Disposition:** `DEFER / OWNER-TRANSITION-EVIDENCE-BLOCKED`.

## 7. C4 — internalization / externalization

No first-class cut-movement transition relation exists.

**Disposition:** `DEFER / RELATION-BLOCKED`.

## 8. C5 — `OperationalClaimUseDisposition`

Claim Standing still has no real production downstream settlement/continuation consumer. Existing Run/Provider/Tool disposition surfaces consume stronger owner-native facts directly.

**Disposition:** `DEFER / NO DELETION-ESSENTIAL CONSUMER`.

## 9. C6 — Agent→Agent delegation / revocation

No first-class Agent→Agent delegation lifecycle exists.

**Disposition:** `DEFER / RELATION-BLOCKED`.

## 10. C7 — federation partition / branch / reconciliation

No first-class partition→branch→reconciliation relation exists.

**Disposition:** `DEFER / RELATION-BLOCKED`.

## 11. C8 — cross-implementation invariance

One current Harness implementation family still dominates. Internal adapters/modules do not create independent implementation evidence.

**Disposition:** `STANDING FALSIFICATION PROGRAMME / NOT NEXT STANDALONE BRANCH`.

## 12. C9 — wheel/public-API release-contract currentness

This candidate has a real current red gate and requires no semantic invention.

### 12.1 Direct wheel failure

Extra closeout wheel smoke from repair 148:

`job-01a01690-c408-70e3-b44c-0ea797d4ef69`.

The wheel built successfully but `scripts/check_wheel.py` failed:

`installed API/version differs`.

### 12.2 Exact mismatch

Fresh post-closeout API diff on canonical `df5195e...`:

`job-01a01697-6b29-7013-a7e6-e7ed7fbcf107`.

Observed:

- actual public API exports = 73;
- wheel checker expected exports = 69;
- missing from wheel checker exactly:
  - `OperationalClaimEvidenceRole`;
  - `OperationalClaimRef`;
  - `OperationalClaimStandingView`;
  - `project_operational_claim_standing_view`;
- stale checker-only members = none.

### 12.3 Authority cross-check

The same four exports are independently current in:

- `src/ordivon_harness/api.py::__all__`;
- `tests/test_public_api.py::EXPECTED_API`;
- `scripts/check_docs.py::STABLE_API`;
- Claim Standing acceptance/closeout 132/133, which explicitly admits them as current public product surfaces.

Therefore the mismatch is not a debate over API policy. It is one stale release checker projection.

### 12.4 Destructive testability

Very high and exact:

- pre-repair wheel/API consistency test must be red by exactly these four members;
- after repair the wheel must install in isolation and expose exactly the current stable API;
- Host must remain absent from base wheel;
- version/root/API checks must remain strict;
- no public API addition/removal is authorized by the branch.

### 12.5 Architecture / owner boundary

Clean. `scripts/check_wheel.py` is already a release-verification owner. Repairing its stale expected set does not move semantic ownership, change runtime behavior or invent domain relations.

### 12.6 Engineering leverage

High relative to cost: a currently red release gate prevents a whole-wheel acceptance path even though source/unit/docs/evidence contracts are green. Fixing it restores agreement among already-authoritative public API projections.

**Disposition:** `READY / STRONGEST CURRENT DIRECT REPAIR CANDIDATE`.

## 13. C10 — other current pressure scan

Current non-wheel repository gates were re-run on `df5195e...`:

- docs: valid;
- dependencies: valid;
- evidence: valid.

No competing red current gate was found in that bounded scan.

A first API-diff probe using system Python failed mechanically because project dependency `anc_canonical` was not installed in that interpreter. The same read-only probe was immediately rerun under `uv run` and succeeded; this is probe setup error, not product evidence.

## 14. Typed comparison

| Candidate | Direct now? | Real current surface | Fixture invents semantics? | Destructive power now | Disposition |
|---|---|---|---|---|---|
| C1 dependency | No | no relation | Yes | blocked | Defer |
| C2 directional provider OPUR | endpoint only | no transition T | Yes for T | blocked | Defer |
| C3 locus migration | No pair | unhealthy owner state | Yes if forced | blocked | Defer |
| C4 internalization | No | adjacent only | Yes | blocked | Defer |
| C5 Claim UseDisposition | conceptual | no consumer | unused abstraction | low | Defer |
| C6 Agent delegation | No | no relation | Yes | blocked | Defer |
| C7 federation branch | No | no relation | Yes | blocked | Defer |
| C8 cross-implementation | criterion yes | insufficient diversity | fake-independence risk | limited | Standing |
| **C9 wheel API currentness** | **Yes** | **red release gate + exact current API authority** | **No** | **very high** | **SELECT** |

No scalar score produced the result. C9 is the only candidate with a current executable release falsifier, exact expected repair surface and no need to manufacture semantics.

## 15. Tournament result

**SELECTED NEXT ENGINEERING / RELEASE-CURRENTNESS BRANCH:**

# Wheel Public API Contract Currentness Repair v1

This is not Campaign 7, not HaF62 and not a new Harness semantic programme.

## 16. Required prebinding

Before modifying `scripts/check_wheel.py`, freeze falsifiers that prove:

1. current source `api.__all__` equals `tests/test_public_api.py::EXPECTED_API`;
2. current source API equals `scripts/check_docs.py::STABLE_API`;
3. pre-repair `scripts/check_wheel.py::EXPECTED_API` differs by exactly the four current Claim Standing exports and no stale extras;
4. the repair may update only the wheel expected API/currentness test surface, not source public exports;
5. post-repair all three expected API projections are exactly equal;
6. isolated wheel smoke passes API/root/version/Host-absence checks;
7. full deterministic suite and existing release gates remain green.

A focused permanent consistency falsifier should prevent future wheel/API drift without creating a new semantic registry. It may compare the existing release/test contract sets directly; it must not become a new fourth API authority.

## 17. Explicit non-selections

Still not selected:

- Campaign 7;
- HaF62;
- generic OCSS dependency graph;
- generic `Preserves_U` transition implementation;
- locus/internalization machinery;
- `OperationalClaimUseDisposition`;
- Agent→Agent delegation;
- federation branch machinery;
- cross-implementation universality;
- public Claim Standing API removal.

## 18. Current standing

- `SelectedHarnessEngineeringBranch = Wheel Public API Contract Currentness Repair v1`.
- `NextHarnessResearchCampaign = UNKNOWN`.
- `NextHarnessFoundationRoute = UNKNOWN`.
- HaF0–HaF61 remain frozen.
- HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.
