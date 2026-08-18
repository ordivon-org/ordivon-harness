# 150 — WHEEL PUBLIC API CONTRACT CURRENTNESS REPAIR v1

**Selection authority:** Tournament 149.  
**Starting canonical:** `06270645500eb5b11cf32258c3fd289759df6b8d`.  
**Task:** `task:harness-wheel-public-api-currentness-repair-v1-20260819`.

## 1. Goal

Restore the isolated wheel release gate by updating only the stale `scripts/check_wheel.py::EXPECTED_API` projection to the already-authorized current public API.

## 2. Prebound current authority

Before repair these three projections already agree on 73 members:

- `src/ordivon_harness/api.py::__all__`;
- `tests/test_public_api.py::EXPECTED_API`;
- `scripts/check_docs.py::STABLE_API`.

The wheel checker has 69 and is missing exactly:

- `OperationalClaimEvidenceRole`;
- `OperationalClaimRef`;
- `OperationalClaimStandingView`;
- `project_operational_claim_standing_view`.

No wheel-only stale exports exist.

## 3. Required focused falsifier

A permanent consistency test must fail before repair and pass after repair by asserting:

`source public API == public API test contract == docs stable API == wheel EXPECTED_API`.

It also explicitly requires the four Claim Standing exports to remain present in the agreed contract.

The test is a consistency guard over existing authorities; it is not a new public API authority.

## 4. Source ceiling

Allowed:

- add exactly the four current exports to `scripts/check_wheel.py::EXPECTED_API`;
- add the focused consistency test;
- research closeout/currentness docs.

Not allowed:

- modifying `src/ordivon_harness/api.py` or any production `src/`;
- removing current Claim Standing exports;
- adding unrelated public API members;
- creating a new central API registry;
- changing wheel root/Host/version/dependency safety checks.

## 5. Acceptance

Classify `WHEEL_PUBLIC_API_CURRENTNESS_REPAIR_ACCEPTED` only if:

- focused pre-repair test is red by the exact current mismatch;
- post-repair focused test is green;
- `scripts/check_wheel.py` diff adds exactly the four authorized names to EXPECTED_API;
- isolated wheel smoke passes;
- base wheel remains Host-free;
- installed API/version/root checks remain strict;
- docs/dependency/evidence/public API gates remain green;
- full deterministic suite remains green;
- no production `src/` changes occur.

No Campaign 7, HaF62 or semantic programme is created. A fresh typed frontier tournament is required after closeout.
