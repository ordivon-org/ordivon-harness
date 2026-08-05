---
schema_version: 1
id: harness.start
title: Ordivon Harness
type: start
profile: organization
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - user
  - builder
  - operator
  - agent
updated: 2026-08-05
summary: Public entry to current Host-backed Agent Run execution and the staged independent Harness persistence foundation.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.quickstart
  - harness.status
  - harness.architecture
  - harness.compatibility
  - harness.verification
  - harness.operations
  - harness.data-privacy
  - harness.releases
  - harness.authority
---
# Ordivon Harness

Ordivon Harness keeps one Agent Run understandable and recoverable when a model, Provider process, Tool response, or local process fails.

The current production Runner binds execution to a durable Host Assignment, adapts replaceable Providers, constrains and records Tool use, checkpoints public Run state, and produces evidence that Host or a domain verifier can evaluate. P0 now also provides a separate caller-neutral Run Contract and independent Journal/CAS foundation; the production Runner has not cut over to it.

```text
Host Task and Assignment
→ Harness Context and ToolGrant
→ Provider Call
→ model Tool request
→ durable Tool Step intent/fence
→ Runtime physical execution
→ Tool Observation and Run Snapshot
→ Completion Proposal
→ Host/domain verification and Task outcome
```

## Responsibility boundary

| Concern | Canonical owner | Harness relationship |
| --- | --- | --- |
| Task identity, Task Attempt, commitments, verification admission and Task outcome | `ordivon-host` | required authority for the current production path and future foreign-Run admission |
| Harness Run, Provider Call, Tool Step, Run Snapshot, resume/recovery and completion-proposal semantics | `ordivon-harness` | owned here; current bytes remain Host-backed while P0 migration is incomplete |
| Workspace, Job, process tree, Artifact and physical side-effect truth | `ordivon-runtime` | invoked and observed through Host Runtime client |
| authoritative world state and semantic completion | domain system or verifier | Harness only proposes completion |
| model inference and hidden Provider session | DeepSeek, Codex App Server, Hermes ACP or another adapter | replaceable execution source, not durable Task truth |

For the current production path, Host stores Harness extension bytes and admits their events while Harness owns their schemas and lifecycle meaning. The P0 independent store is an explicit additive surface and is not dual-written by that path. Storage location does not transfer semantic ownership.

## Status

Harness is an operational engineering prototype for owner-trusted local work and pre-1.0 as a public package. Its current Runner has durable Host-backed Provider Call and Tool Step recovery, semantic-history validation, DeepSeek/Codex/Hermes adapters, cancellation, bounded budgets, and real evidence across several pinned dependency graphs.

The P0 independent path now has a caller-neutral Contract, SQLite Journal/CAS, revision and lease fencing, full Doctor, verified backup/restore, an event-sourced Provider/Tool/Snapshot continuity implementation, and a real no-Tool Agent Loop bridge. It is not yet selected by the production Runner and does not yet execute Runtime Tools independently. Harness remains neither a general workflow engine, Provider router, multi-Agent scheduler, hosted sandbox, nor independent Task database. See [`docs/STATUS.md`](docs/STATUS.md) and [`docs/P0-INDEPENDENT-PERSISTENCE.md`](docs/P0-INDEPENDENT-PERSISTENCE.md).

## What works

- Host-backed Task Attempt, Assignment and Run admission;
- exact Host revision and Protocol pins with a checked `uv.lock`;
- durable Provider Call claim, dispatch, result, failure, UNKNOWN and replay semantics;
- durable Tool Step intent, dispatch fence, receipt, reconciliation and cancellation;
- Run Snapshot, pause, resume, budget continuity and process-replacement recovery;
- ToolGrant filtering and Runtime catalog binding;
- DeepSeek turn adapter, Codex App Server adapter and Hermes ACP adapter;
- independent completion proposal, verification admission and outcome handling;
- semantic Doctor over current Host-backed Harness history;
- caller-neutral `HarnessRunContract` and independent `SQLiteHarnessStore`;
- independent Run Journal/CAS with revision and lease fencing;
- independent Provider Call, Tool Step, Snapshot and pause continuity over the Event chain;
- version-2 Harness-owned Runtime dispatch fences without Host Task fields;
- real no-Tool Agent Loop execution, pause/resume and durable Provider replay without Host state;
- verified online backup, tamper detection and restore to a fresh state root;
- operator `status`, `inspect`, `handoff`, `cancel` and `recover` paths, plus explicit `store-*` operations.

## What it does not do

- own Task or Goal truth;
- cut the production Runner over to the independent Journal before Provider Call, Tool Step, Snapshot, recovery and Host-adapter gates pass;
- treat Provider hidden state as authoritative continuity;
- infer semantic completion from Runtime success;
- provide hostile multi-tenant isolation;
- support mid-call Provider migration;
- guarantee arbitrary Tool retry safety;
- automatically choose the “best” Provider;
- expose every internal persistence type as stable API.

## Requirements

- Python 3.12;
- `uv` for exact graph installation, lock validation, isolated tooling and wheel smoke tests;
- Linux for the canonical trusted-local operational path;
- exact `ordivon-host` and `ordivon-protocol` revisions pinned in `pyproject.toml` and `uv.lock` for the current production package graph;
- Ordivon Runtime for real Tool execution;
- an explicit Provider adapter for model inference.

## Quick start

Install the pinned dependency graph:

```bash
uv python install 3.12
uv sync --locked
uv lock --check
```

Run the portable contract and verify the built distribution:

```bash
uv run python -m compileall -q src tests scripts evals
uvx ruff==0.15.17 check src tests scripts
uv run python -W error::ResourceWarning -m unittest discover -s tests -v
uv run python scripts/check_dependencies.py
uv run python scripts/check_docs.py
uv run python scripts/check_evidence.py
uv run python scripts/demo_deterministic_run.py
scripts/local-acceptance check
uv build --wheel --out-dir /tmp/ordivon-harness-wheel
uv run python scripts/check_wheel.py /tmp/ordivon-harness-wheel
```

The wheel check validates metadata, exact dependency pins, the CLI entry point and an isolated installation. The first deterministic and live journeys are documented in [`docs/QUICKSTART.md`](docs/QUICKSTART.md).

## Domain-owned Tool loops

Version `0.6` exposes a dependency-inverted domain Tool seam for projects that already own their durable Actor or Contest boundary:

```python
from ordivon_harness.api import (
    DomainToolCatalog,
    DomainToolLoopPlan,
    DomainToolLoopRunner,
)
```

A domain supplies immutable Tool definitions, a Bridge implementation, a per-loop grant, and domain effect evidence. Harness supplies the Provider-neutral model loop, budgets, cancellation, stopping, and Tool-call observations. Harness does not import the domain and does not claim domain truth. See [`docs/DOMAIN-TOOL-BRIDGE-P0.md`](docs/DOMAIN-TOOL-BRIDGE-P0.md).

## Public API

New application integrations should import from the stable facade:

```python
from ordivon_harness.api import (
    CompletionMode,
    HarnessRunner,
    HarnessRunPlan,
    TaskContract,
    ToolGrant,
)
```

The package root retains historical pre-1.0 exports for compatibility. Provider drivers, owner-local persistence records and recovery implementation types remain integration or internal APIs even when old root aliases still exist. See [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).

## Operator interface

Current Host-backed operations:

```bash
ordivon-harness --state-root /var/lib/ordivon/host status TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host inspect TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host handoff TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host cancel TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host recover TASK_ID
```

Independent P0 Store operations:

```bash
ordivon-harness --harness-state-root /var/lib/ordivon/harness store-init
ordivon-harness --harness-state-root /var/lib/ordivon/harness store-doctor
ordivon-harness --harness-state-root /var/lib/ordivon/harness store-inspect HARNESS_RUN_ID
ordivon-harness --harness-state-root /var/lib/ordivon/harness store-events HARNESS_RUN_ID
ordivon-harness --harness-state-root /var/lib/ordivon/harness store-backup BACKUP_DIR
ordivon-harness store-verify-backup BACKUP_DIR
ordivon-harness store-restore BACKUP_DIR NEW_STATE_ROOT
```

`inspect` and `handoff` require neither Runtime nor Provider access. Recovery never authorizes blind redispatch of an uncertain Provider or Tool effect. The `store-*` surface does not execute or resume the current production Agent loop.

## Documentation map

| Need | Start here |
| --- | --- |
| install and run first journeys | [`docs/QUICKSTART.md`](docs/QUICKSTART.md) |
| current maturity and limits | [`docs/STATUS.md`](docs/STATUS.md) |
| architecture and ownership | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| dependency, object and upgrade compatibility | [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) |
| claim-to-evidence map | [`docs/VERIFICATION.md`](docs/VERIFICATION.md) |
| configuration and operations | [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
| independent P0 Journal/CAS and cutover status | [`docs/P0-INDEPENDENT-PERSISTENCE.md`](docs/P0-INDEPENDENT-PERSISTENCE.md) |
| sensitive data, retention and deletion | [`docs/DATA_AND_PRIVACY.md`](docs/DATA_AND_PRIVACY.md) |
| release and deprecation gates | [`docs/RELEASES.md`](docs/RELEASES.md) |
| canonical document ownership | [`docs/authority.md`](docs/authority.md) |
| repository contribution | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| private vulnerability reporting | [`SECURITY.md`](SECURITY.md) |

Historical phase reports and `evidence/` receipts preserve earlier dependency graphs. They do not automatically certify current `main`.

## Security and data

Harness may send bounded Context and Tool observations to external Providers and persist prompts, model output, Tool arguments, Runtime references, traces and receipts in Host CAS. Future migrated Runs may retain the same classes in the independent Harness CAS according to their privacy policy. It does not automatically redact sensitive content. Read [`SECURITY.md`](SECURITY.md) and [`docs/DATA_AND_PRIVACY.md`](docs/DATA_AND_PRIVACY.md).

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
