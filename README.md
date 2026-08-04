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
updated: 2026-08-04
summary: Public entry to Host-native Agent Run execution, Provider adaptation, Tool checkpointing, evidence, resume, and recovery.
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

It binds execution to a durable Host Assignment, adapts replaceable Providers, constrains and records Tool use, checkpoints public Run state, and produces evidence that Host or a domain verifier can evaluate.

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
| Task identity, revision fencing, Journal/CAS admission, commitments, verification admission, outcome | `ordivon-host` | required Host-native authority |
| Assignment, Provider Call, Tool Step, Run Snapshot, resume/recovery and completion-proposal semantics | `ordivon-harness` | owned here |
| Workspace, Job, process tree, Artifact and physical side-effect truth | `ordivon-runtime` | invoked and observed through Host Runtime client |
| authoritative world state and semantic completion | domain system or verifier | Harness only proposes completion |
| model inference and hidden Provider session | DeepSeek, Codex App Server, Hermes ACP or another adapter | replaceable execution source, not durable Task truth |

Host stores Harness extension bytes and admits their events; Harness owns their schemas and lifecycle meaning. Storage does not transfer semantic ownership.

## Status

Harness is an operational engineering prototype for owner-trusted local work and pre-1.0 as a public package. It has durable Provider Call and Tool Step recovery, semantic-history validation, DeepSeek/Codex/Hermes adapters, cancellation, bounded budgets, and real evidence across several pinned dependency graphs.

It is not a general workflow engine, Provider router, multi-Agent scheduler, hosted sandbox, or independent Task database. See [`docs/STATUS.md`](docs/STATUS.md).

## What works

- Host-backed Task Attempt, Assignment and Run admission;
- exact Host revision and Protocol pins with a checked `uv.lock`;
- durable Provider Call claim, dispatch, result, failure, UNKNOWN and replay semantics;
- durable Tool Step intent, dispatch fence, receipt, reconciliation and cancellation;
- Run Snapshot, pause, resume, budget continuity and process-replacement recovery;
- ToolGrant filtering and Runtime catalog binding;
- DeepSeek turn adapter, Codex App Server adapter and Hermes ACP adapter;
- independent completion proposal, verification admission and outcome handling;
- semantic Doctor over Harness history;
- operator `status`, `inspect`, `handoff`, `cancel` and `recover` paths.

## What it does not do

- own Task or Goal truth;
- create another Journal, database or scheduler;
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
- exact `ordivon-host` and `ordivon-protocol` revisions pinned in `pyproject.toml` and `uv.lock`;
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

```bash
ordivon-harness --state-root /var/lib/ordivon/host status TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host inspect TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host handoff TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host cancel TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host recover TASK_ID
```

`inspect` and `handoff` require neither Runtime nor Provider access. Recovery never authorizes blind redispatch of an uncertain Provider or Tool effect.

## Documentation map

| Need | Start here |
| --- | --- |
| install and run first journeys | [`docs/QUICKSTART.md`](docs/QUICKSTART.md) |
| current maturity and limits | [`docs/STATUS.md`](docs/STATUS.md) |
| architecture and ownership | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| dependency, object and upgrade compatibility | [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) |
| claim-to-evidence map | [`docs/VERIFICATION.md`](docs/VERIFICATION.md) |
| configuration and operations | [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
| sensitive data, retention and deletion | [`docs/DATA_AND_PRIVACY.md`](docs/DATA_AND_PRIVACY.md) |
| release and deprecation gates | [`docs/RELEASES.md`](docs/RELEASES.md) |
| canonical document ownership | [`docs/authority.md`](docs/authority.md) |
| repository contribution | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| private vulnerability reporting | [`SECURITY.md`](SECURITY.md) |

Historical phase reports and `evidence/` receipts preserve earlier dependency graphs. They do not automatically certify current `main`.

## Security and data

Harness may send bounded Context and Tool observations to external Providers and persist prompts, model output, Tool arguments, Runtime references, traces and receipts in Host CAS. It does not automatically redact sensitive content. Read [`SECURITY.md`](SECURITY.md) and [`docs/DATA_AND_PRIVACY.md`](docs/DATA_AND_PRIVACY.md).

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
