# 157 — POST-BATCH-SEARCH EVIDENCE CURRENTNESS REPAIR v1
# Result and Closeout

**Trigger:** canonical batch-search composition `51b942c5719749fbc3e9ba57ef1bf72ab5dd9a81` changed implementation paths covered by the only then-current verified Harness evidence receipt.

**Prebound contract commit:** `79239bdb71e51e5837d3d8b5358561a7e23c01d8`.

## 1. Classification

`POST_BATCH_SEARCH_EVIDENCE_CURRENTNESS_REPAIR_ACCEPTED`.

The immutable unreachable-abandonment retirement receipt remains valid historical evidence for `46030ae7d5725cffcad4686707d391ba29fd7f01`; it no longer certifies whole-current Harness implementation after `51b942c...`. No replacement verified receipt was minted.

## 2. Baseline-red

Runtime Job: `job-01a04793-1d5d-7a30-977c-c4ad1448ca59`.

Before index modification, the prebound typed-ingestion suite failed exactly because the index still said `verified` while the correct expectation said `historical`. The complete evidence checker independently failed on the same claim and exact invalidating set:

- `src/ordivon_harness/ordivon/loop.py`;
- `src/ordivon_harness/ordivon/run_recovery.py`;
- `src/ordivon_harness/ordivon/runtime_lowering.py`;
- `src/ordivon_harness/ordivon/sqlite_runtime_bridge.py`.

No unrelated evidence defect was required to obtain the red baseline.

## 3. Minimal repair

Immutable receipt file:

`evidence/harness-unreachable-abandonment-retirement-v1.json`

SHA-256 before and after repair:

`f0f415fe6677b2d1a8089510ac83c8a5b7a3f5a51a064aaf65e21ef0ffd3d6b1`.

Only currentness representation changed:

- evidence-index status `verified -> historical`;
- index scope records the exact `51b942c` invalidation boundary;
- typed-ingestion permanently binds the immutable receipt bytes/revision as historical and asserts the exact four invalidating paths;
- research recovery-root current census is updated from the actual `79 historical / 1 verified` to `80 historical / 0 verified`.

Historical authority-publication JSON was not rewritten.

## 4. Focused acceptance

Runtime Job: `job-01a04794-12b6-7a51-bacb-8fc360e64c11`.

Passed:

- typed evidence/currentness tests: 6/6;
- complete evidence contract: `80 historical / 0 verified`;
- immutable receipt SHA unchanged;
- `git diff --check`.

## 5. Complete owner acceptance

Runtime Job: `job-01a04794-43d5-7bc1-864f-9fbbc8ce504f`.

Result:

- owner environment doctor: valid;
- dependency contract: valid, protocol `420dc356...`, Host absent from dependency boundary;
- ruff: passed;
- complete test suite: **566 tests OK**, **3 skipped**;
- elapsed test time: 112.509 seconds.

## 6. Truth-role consequence

This repair reinforces:

`historically valid receipt != whole-current verified receipt`

`bounded deletion proof at 46030ae != automatic certification of later observation/recovery implementation`

`zero verified current receipts is preferable to manufacturing one for symmetry`.

The retirement result remains usable at its tested revision. Current batch-search acceptance is established by its own current tests/gates, not by relabeling the older retirement receipt.

## 7. Explicit non-results

This repair does not rerun the 284-store census, does not resurrect retired Abandonment/Disposition semantics, does not change batch-search product behavior, and does not create a new generic evidence registry.

## 8. Closeout

**POST-BATCH-SEARCH EVIDENCE CURRENTNESS REPAIR v1 COMPLETE.**

Harness evidence classification once again agrees with owner-local currentness law after canonical batch-search composition.
