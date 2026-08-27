# 155 — POST-HTTPX EVIDENCE CURRENTNESS REPAIR v1
# Result and Closeout

**Trigger:** Harness owner-publication preparation for Atlas coverage reconciliation.
**Observed remote source:** `917087e94348f2fb94dd891455793c27fc7edfd6`.
**Owner-publication boundary materialization:** `7d6bf9cf81d3444cf0599f761a31dc1494286970`.
**Prebound repair contract/tests:** `93d96b9fbeb37e5e5ba672e97987550ac975869c`.

## 1. Classification

`POST_HTTPX_EVIDENCE_CURRENTNESS_REPAIR_ACCEPTED`.

The current evidence index again agrees with its own verified-currentness law after the HTTPX transport transition. No product source, immutable receipt byte, Foundation, Campaign, or external authority was changed to obtain this result.

## 2. Discovery path

Atlas admission was intentionally blocked until Harness could publish owner-native research currentness. During that preparation, the existing complete evidence gate was run against the exact current remote Harness source rather than assuming the repository was green because the latest transport work had closed successfully.

The gate failed on:

`harness.execution.source-reconciliation-structured-observation-v1`.

The receipt is bound to implementation revision:

`e983c79f5582160b37ac56c1898efa80e486880d`.

It was still indexed as `verified`, but current source had later changed three paths inside the checker's verified implementation set:

- `pyproject.toml`;
- `src/ordivon_harness/ordivon/deepseek.py`;
- `uv.lock`.

The relevant later transition is `917087e`, which delegates DeepSeek transport to pinned HTTPX. The old receipt remains valid evidence for its own source graph; it no longer certifies the whole current graph.

## 3. Frozen baseline-red

Prebind commit:

`93d96b9fbeb37e5e5ba672e97987550ac975869c`.

Runtime baseline-red Job:

`job-01a03f88-cf9d-76f1-9644-93413a0aaa73`.

Observed independently:

1. typed-ingestion expectation failed because index said `verified` while the prebound correct expectation said `historical`;
2. the complete evidence gate failed because `e983c79...` had the three exact invalidating paths above;
3. the remaining focused currentness/binding tests passed.

Thus the failure was reproduced before the index was modified.

## 4. Minimal repair

The immutable receipt remained byte-identical with SHA-256:

`db9d22a113a1e7b5f4f4ea882d71e6aec91da2a6e61c16f5dc0abd8e821b28ea`.

Only currentness representation changed:

- index status: `verified -> historical`;
- index scope now records the HTTPX invalidation boundary;
- research evidence census: `76 historical / 1 verified -> 77 historical / 0 verified`;
- permanent test now requires `e983c79...` to be non-current with the exact invalidating path set.

No replacement `verified` receipt was minted. A zero count is more truthful than manufacturing current evidence for metric symmetry.

## 5. Focused acceptance

Runtime Job:

`job-01a03f8a-7afe-7043-bda6-7ea410e9edfe`.

Passed:

- 6/6 typed evidence/currentness tests;
- complete evidence contract: `77 historical / 0 verified`;
- documentation contract;
- dependency contract;
- `git diff --check`.

## 6. Full deterministic acceptance

The first direct system-Python discovery attempt was mechanically invalid because the repository package/dependency environment was absent; that setup error is not product evidence. The repository-authoritative path was then used exactly as documented:

`uv run python -m unittest discover -s tests -v`.

Runtime Job:

`job-01a03f8a-f55c-7fb0-8b73-cd29ad710463`.

Result:

- **538 tests**;
- **OK**;
- **3 skipped**;
- 108.934 seconds.

## 7. Truth-role consequence

This repair reinforces three already-established distinctions:

`historical evidence != false evidence`
`bounded research standing != whole-current implementation certification`
`repository latest/current transport work != automatically current evidence index`.

The Atlas registration workflow did not become Harness authority. It acted as a consumer pressure that forced the owner to re-run its own currentness rules before exporting a machine publication.

## 8. Explicit non-results

This repair does not:

- revoke source-reconciliation research standing at its tested revision;
- alter HTTPX transport semantics or re-run the 153 experiment as a new experiment;
- create a replacement verified receipt;
- create Campaign 7 or HaF62;
- claim the entire Harness research corpus is complete;
- grant Atlas authority to decide Harness standing.

## 9. Closeout

**POST-HTTPX EVIDENCE CURRENTNESS REPAIR v1 COMPLETE.**

Harness is now eligible to resume owner-native research publication preparation from a green owner-side currentness surface.
