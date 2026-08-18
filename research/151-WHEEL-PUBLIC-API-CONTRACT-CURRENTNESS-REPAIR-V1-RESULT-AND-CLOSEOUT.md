# 151 — WHEEL PUBLIC API CONTRACT CURRENTNESS REPAIR v1
# Result and Closeout

**Task:** `task:harness-wheel-public-api-currentness-repair-v1-20260819`  
**Selection authority:** Tournament 149.  
**Prebind commit:** `45e8385be456d32b0c510768867d42a04295d3a2`.  
**Repair commit:** `28eba0c8ea9f58ef7a96ca8b7add37b5f3e3cf17`.  
**Starting canonical:** `06270645500eb5b11cf32258c3fd289759df6b8d`.

## 1. Classification

`WHEEL_PUBLIC_API_CURRENTNESS_REPAIR_ACCEPTED`.

The isolated wheel release contract is current again. No public API or production source changed; only the stale wheel expected-API projection was updated by the four already-authorized Claim Standing exports.

## 2. Baseline-red

Prebound focused test:

`tests/test_wheel_public_api_contract.py`.

Runtime Job:

`job-01a0169a-c13f-7471-8c16-96fa3bd2689c`.

Result:

- 2 tests;
- 1 pass;
- 1 failure.

The failing equality showed `scripts/check_wheel.py::EXPECTED_API` lacked exactly:

- `OperationalClaimEvidenceRole`;
- `OperationalClaimRef`;
- `OperationalClaimStandingView`;
- `project_operational_claim_standing_view`.

No other mismatch existed.

## 3. Repair

Only:

`scripts/check_wheel.py`

changed in the implementation commit.

Diff:

- 4 insertions;
- 0 deletions.

No `src/` file changed.

The four inserted symbols were already current in:

- source `api.__all__`;
- `tests/test_public_api.py::EXPECTED_API`;
- `scripts/check_docs.py::STABLE_API`;
- Claim Standing acceptance/closeout 132/133.

Therefore this is release-currentness repair, not API expansion.

## 4. Focused and repository acceptance

Runtime Job:

`job-01a0169b-cbb7-7db0-9923-f878064d44d2`.

Passed:

- 2/2 wheel API consistency tests;
- 6/6 current public API tests;
- Ruff;
- documentation contract;
- dependency contract;
- evidence contract;
- `git diff --check`.

## 5. Isolated wheel acceptance

Runtime Job:

`job-01a0169c-0139-7313-8f57-0cee0b4e6fd2`.

The wheel built and the real isolated wheel checker passed.

Observed result:

- status = `passed`;
- version = `0.6.0`;
- installedVersion = `0.6.0`;
- hostFreeCoreVerified = `true`;
- cliCommandsVerified = `14`;
- installed API/root/version checks passed;
- Host remained absent from the base wheel.

This closes the exact release path that had failed before repair.

## 6. Full deterministic acceptance

Runtime Job:

`job-01a0169c-7339-7bd3-83fc-191af1362d9e`.

Result:

- **452 tests**;
- **OK**;
- **3 skipped**;
- 101.818 seconds.

The prior suite had 450 tests. The increase to 452 is exactly the two permanent wheel/public-API consistency tests.

## 7. Currentness standing

Current public API projections now agree across:

`source api.__all__ = public API tests = docs STABLE_API = wheel EXPECTED_API`.

The focused consistency test is a guard over those existing authorities; it does not become a new semantic API authority.

## 8. Explicit non-results

This repair does not:

- add or remove public product API;
- modify Claim Standing semantics;
- change package dependencies;
- add Host to the base wheel;
- create Campaign 7;
- create HaF62;
- resolve OCSS dependency, directional/locus/internalization OPUR, Claim UseDisposition, delegation/federation or cross-implementation questions.

## 9. Closeout

**WHEEL PUBLIC API CONTRACT CURRENTNESS REPAIR v1 COMPLETE.**

- wheel release gate: current / passed;
- API consistency guard: permanent;
- production source change: none;
- repair surface: one release checker, four names;
- full suite: 452 OK, 3 skipped;
- next Harness frontier: UNKNOWN pending fresh typed tournament.
