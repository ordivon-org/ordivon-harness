---
schema_version: 1
id: harness.verification
title: Harness Verification
type: reference
profile: engineering
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - builder
  - operator
  - researcher
  - agent
updated: 2026-08-19
summary: Claim classes, evidence strength, historical evidence interpretation and current release gates.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.status
  - harness.compatibility
  - harness.releases
---
# Harness Verification

## Evidence classes

| Evidence | Proves | Does not prove |
| --- | --- | --- |
| deterministic unit/integration test | current source invariant under controlled inputs | live Provider or Runtime behavior |
| frozen fixture | a named failure trajectory and expected repair | arbitrary repositories or Providers |
| live receipt | one real journey on an exact dependency graph | current `main` after later changes |
| immutable research projection/result | one bounded owner/research observation bound to a tested implementation lineage | whole-current-product certification after later source changes |
| historical closeout/report | design evolution and prior decisions | current implementation correctness |

No implementation-bound evidence should be cited without its Harness/implementation revision and dependency context.

## Current portable gate

The current release gate includes:

- compile and Ruff;
- complete deterministic suite with `ResourceWarning` as error;
- exact dependency and lockfile checks;
- Host import-boundary tests;
- stable API contract tests;
- semantic-history validation tests;
- documentation and evidence-index validation;
- wheel metadata validation, isolated installation, CLI smoke testing and dependency audit;
- bounded atomic Event-batch replay/rollback tests and the deterministic scale smoke.

## Evidence index and revision binding

`evidence/index.json` classifies every repository `evidence/*.json` object and `scripts/check_evidence.py` enforces exact file correspondence, revision binding and `verified` currentness.

Two revision-binding modes are supported:

- **embedded** — the default legacy receipt mode. The payload itself must carry the exact implementation/source revision recorded by the index.
- **index-creation-lineage** — explicit opt-in for immutable research projections/results whose frozen payload shape does not carry the legacy receipt revision field. The index revision must be an ancestor of the evidence file's unique Git creation commit, no invalidating implementation path may change before evidence creation, and the evidence bytes must remain identical to the creation commit. Recognized embedded tested-revision hints, when present, must agree with the index.

The second mode does not make the index semantic truth owner. It binds repository provenance/currentness without rewriting frozen evidence bytes.

A `verified` entry is current only while no later invalidating implementation path has changed after its bound revision. Once that condition fails, the evidence remains useful historical evidence but must be demoted rather than silently certifying current code.

## P0 scale acceptance

The full P0 persistence closeout uses:

```bash
uv run python scripts/harness_p0_scale_acceptance.py \
  --runs 1000 \
  --events-per-run 100 \
  --batch-size 99 \
  --output evidence/hho-p0-scale-1000x100-<revision>.json
```

The receipt must bind the exact implementation revision and prove 1,000 Runs, 100,000 Events, a healthy full-history Doctor after reopen, exact object-reference/file agreement, and sampled current-Run inspection below the recorded one-second gate. Thresholds and machine measurements remain in the receipt rather than becoming timeless prose.

## Historical live receipts

`evidence/index.json` classifies repository evidence. Existing Codex, Hermes, DeepSeek, Runtime and replacement/recovery receipts are historical because they bind commits before current `main`. They remain valuable evidence for those trajectories but must not be described as certification of current code.

## Current live acceptance

A current release-changing Provider, Runtime, recovery or completion path should produce a new receipt containing:

- Harness Git commit and package version;
- Protocol revision, and Host/caller revision only when that caller participates in the exercised graph;
- Runtime identity and Tool catalog digest when Runtime Tools participate;
- Provider adapter/model identity;
- caller reference and Harness Run identity;
- relevant Tool Step and Provider Call identities;
- final status and explicit unknowns;
- receipt integrity digest;
- limitations.

The canonical command is `scripts/local-acceptance run` on an owner-trusted acceptance environment.

## Claim discipline

Use these terms consistently:

- **operational**: repeatedly exercised in the supported graph;
- **experimental**: implemented and tested, but public behavior may still change;
- **verified in pinned graph**: deterministic/live evidence exists for named revisions;
- **historical**: evidence exists only for an earlier graph;
- **unsupported**: no contract or safe path exists.

Tests and evidence verify bounded behavior. They do not turn Runtime success into semantic Task completion or remove Provider/domain uncertainty.
