# 154 — POST-HTTPX EVIDENCE CURRENTNESS REPAIR v1 — Contract

**Starting remote authority:** `ordivon-harness` remote `refs/heads/main` = `917087e94348f2fb94dd891455793c27fc7edfd6` at admission observation.
**Trigger:** owner-publication preparation independently ran the existing complete evidence gate and reproduced a stale `verified` receipt on untouched current source.
**Publication effect:** blocked until this owner-local currentness defect is resolved.

## Problem

Commit `917087e` correctly changed the current Harness implementation by delegating DeepSeek HTTP/TLS transport to pinned HTTPX and added closeout 153. The evidence index still marked `harness.execution.source-reconciliation-structured-observation-v1` at implementation revision `e983c79...` as `verified` whole-current implementation evidence.

The existing checker proves that this status is no longer true: between `e983c79...` and current source, the verified implementation set changed at `pyproject.toml`, `src/ordivon_harness/ordivon/deepseek.py`, and `uv.lock`.

Therefore:

`historically valid receipt + later invalidating implementation change != verified current receipt`.

This is the same currentness law already used to demote TS11 and older owner-bridge receipts. Atlas admission is not allowed to bypass it.

## Frozen repair scope

The smallest admissible repair is:

1. preserve immutable receipt bytes and implementation revision exactly;
2. change only the stale index classification `verified -> historical` plus scope text explaining the invalidation;
3. update the research-root evidence census from `76 historical / 1 verified` to `77 historical / 0 verified`;
4. update the existing typed-ingestion test so the stale receipt is permanently expected to be historical and `e983c79...` is permanently expected to fail verified-currentness after the HTTPX change;
5. run the complete evidence, documentation and deterministic repository gates;
6. record a closeout without inventing replacement `verified` evidence merely to keep the count nonzero.

## Explicit non-goals

This repair does **not**:

- revoke the bounded research standing of the source-reconciliation or HTTPX closeouts;
- rewrite immutable evidence bytes;
- create a new current receipt without a new evidence-producing experiment;
- change Harness runtime/product semantics;
- select Campaign 7 or HaF62;
- treat Atlas publication as an evidence-currentness authority.

## Baseline-red requirement

Before the index is changed, the prebound typed-ingestion test must fail because the current index still says `verified` while the frozen expectation says `historical`; the complete evidence gate must independently remain red for the same stale-currentness reason.
