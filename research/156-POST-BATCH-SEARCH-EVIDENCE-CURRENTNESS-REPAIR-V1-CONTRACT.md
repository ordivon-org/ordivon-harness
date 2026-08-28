# 156 — POST-BATCH-SEARCH EVIDENCE CURRENTNESS REPAIR v1 — Contract

**Starting remote authority:** `ordivon-harness` remote `refs/heads/main` = `51b942c5719749fbc3e9ba57ef1bf72ab5dd9a81` at admission observation.

**Trigger:** canonical batch-search composition passed functional acceptance, but the owner-native evidence gate independently reproduced one stale whole-current `verified` receipt.

## Problem

Immutable receipt `harness.recovery.unreachable-abandonment-retirement-v1` remains valid for implementation revision `46030ae7d5725cffcad4686707d391ba29fd7f01`, but current canonical batch-search commit `51b942c...` modified four paths inside its verified implementation set: `loop.py`, `run_recovery.py`, `runtime_lowering.py`, and `sqlite_runtime_bridge.py`. The existing checker therefore correctly rejects the old receipt as whole-current verified evidence. The immutable receipt SHA-256 remains `f0f415fe6677b2d1a8089510ac83c8a5b7a3f5a51a064aaf65e21ef0ffd3d6b1`.

## Frozen repair scope

1. Preserve immutable receipt bytes and revision exactly.
2. Prebind typed-ingestion expectation to `historical` and the exact four invalidating paths.
3. Reproduce baseline red before index modification.
4. Change only index status/scope plus current research-root census.
5. Actual pre-repair census is `79 historical / 1 verified`; repaired census must be `80 historical / 0 verified`.
6. Do not rewrite historical authority-publication JSON.
7. Run focused evidence tests and complete owner gate.
8. Do not mint replacement verified evidence without a new evidence-producing experiment.

## Baseline-red requirement

Before changing the index, typed ingestion must fail because the correct prebound expectation says `historical` while the index still says `verified`; `scripts/check_evidence.py` must independently remain red on the same exact four invalidating paths.
