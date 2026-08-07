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
summary: Public entry to caller-neutral Agent Run execution, durable Harness-owned continuity, Runtime bridging, and explicit Host compatibility.
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

The recommended application surface is now caller-neutral: one `HarnessRunContract`, Harness-owned Journal/CAS continuity, Provider/Tool execution, Runtime bridging, and a caller-neutral CompletionProposal. A Host-backed Runner remains as an explicit compatibility path for existing durable Host Assignments; changing the recommended import surface does **not** migrate production state or silently activate the cutover writer.

```text
caller or domain-owned work
→ HarnessRunContract + bounded Context/Tool surface
→ Provider Call
→ model Tool request
→ durable Harness Tool intent/fence
→ Runtime or domain Tool execution
→ Tool Observation + Run Snapshot/Trace
→ caller-neutral CompletionProposal
→ optional Host/domain verification and outcome ownership
```

## Responsibility boundary

| Concern | Canonical owner | Harness relationship |
| --- | --- | --- |
| Task identity, Task Attempt, commitments, verification admission and Task outcome | `ordivon-host` | optional higher-level authority for Host-bound work; not required by the default independent CLI |
| Harness Run, Provider Call, Tool Step, Run Snapshot, resume/recovery and completion-proposal semantics | `ordivon-harness` | owned and durably writable in the independent Journal/CAS; legacy Host-backed bytes remain readable |
| Workspace, Job, process tree, Artifact and physical side-effect truth | `ordivon-runtime` | consumed through a caller-supplied Runtime client on Tool-bearing independent paths |
| authoritative world state and semantic completion | domain system or verifier | Harness only proposes completion |
| model inference and hidden Provider session | DeepSeek, Codex App Server, Hermes ACP or another adapter | replaceable execution source, not durable Task truth |

For retained Host-backed work, Host stores Harness extension bytes and admits their events while Harness owns their schemas and lifecycle meaning. New default CLI operations target the independent Harness Journal/CAS; they do not migrate, dual-write, or reinterpret retained Host state. Storage location does not transfer semantic ownership.

## Status

Harness is an operational engineering prototype for owner-trusted local work and pre-1.0 as a public package. The default CLI now operates caller-neutral independent Runs directly: Contract-in no-Tool DeepSeek execution, durable pause/resume, status/inspection, conservative recovery, Trace, Run Receipt and CompletionProposal all use the Harness Journal/CAS without Host. The historical `HarnessRunner` and its Host-backed Task/Assignment lifecycle remain an explicit compatibility path under `ordivon-harness host ...`.

The independent Tool-bearing path is also implemented in the Python API through caller-supplied `HarnessRuntimeClient` bridges, including observation-only Runtime search and repository-repair trials with response-loss reconciliation. The CLI deliberately does not invent or copy a concrete Runtime transport: Tool-bearing Contract execution fails closed there until the caller supplies the Runtime boundary through `ordivon_harness.api` or `ordivon_harness.core`. A Host-neutral external-executor adapter proves Host and Harness can retain separate histories across response loss. Cutover inventory and append-only receipts still govern migration of retained deployment state; H1 changes the operational entry point, not production roots. Harness remains neither a general workflow engine, Provider router, multi-Agent scheduler, hosted sandbox, nor independent Task database. See [`docs/STATUS.md`](docs/STATUS.md) and [`docs/P0-INDEPENDENT-PERSISTENCE.md`](docs/P0-INDEPENDENT-PERSISTENCE.md).

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
- independent observation-only Runtime search with Harness-owned dispatch fencing and exact-request reconciliation;
- explicit Standalone Runner with restart-safe Trace segments, Run Receipt, Recovery Assessment and CompletionProposal;
- Host-neutral `OrdivonHarnessExternalExecutorAdapter` that exposes the independent Run as a foreign executor without sharing databases;
- active legacy-Run inventory, append-only cutover/rollback receipts, and a fail-closed legacy writer gate;
- caller-neutral `HarnessExecutionBinding` and Host-free Runtime request lowering;
- verified online backup, tamper detection and restore to a fresh state root;
- first-class independent CLI `capabilities`, `run`, `resume`, `status`, `inspect`, `recover` and `doctor` operations;
- explicit `host ...` compatibility commands for retained Task/Assignment-backed operation, plus `store-*` and `cutover-*` controls.

## What it does not do

- own Task or Goal truth;
- silently cut the production Runner over without a verified inventory and explicit cutover receipt;
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
- exact `ordivon-protocol` revision in the base package and exact `ordivon-host` revision in the optional `host` integration extra;
- Ordivon Runtime for real Tool execution;
- an explicit Provider adapter for model inference.

## Quick start

Install the repository development graph, including the pinned Host integration used by the legacy production suite:

```bash
uv python install 3.12
uv sync --locked
uv lock --check
```

A consumer that only needs caller-neutral contracts, independent persistence and the Standalone Runner installs the base wheel. Host-backed APIs require the explicit extra:

```bash
pip install ./ordivon_harness-0.6.0-py3-none-any.whl
pip install "ordivon-harness[host] @ file:///path/to/ordivon_harness-0.6.0-py3-none-any.whl"
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

The wheel check validates metadata, exact dependency pins, a Host-free base installation that completes and reopens a persistent Run, the optional Host integration, and the CLI entry point. The first deterministic and live journeys are documented in [`docs/QUICKSTART.md`](docs/QUICKSTART.md).

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

New Agent applications should import the small Host-free facade:

```python
from ordivon_harness.api import (
    HarnessRunContract,
    SQLiteHarnessStore,
    StandaloneHarnessRunner,
)
```

`ordivon_harness.core` remains the wider Host-free integration surface for advanced Runtime, persistence, recovery, and Provider work.

Applications that intentionally bind execution to the historical Host-backed Runner install the `host` extra and use the explicit compatibility facade:

```python
from ordivon_harness.host_api import (
    CompletionMode,
    HarnessRunner,
    HarnessRunPlan,
    TaskContract,
    ToolGrant,
)
```

The package root retains historical pre-1.0 exports for compatibility. No production state is migrated by importing the new facade. Provider drivers, owner-local persistence records and recovery implementation types remain integration or internal APIs even when old root aliases still exist. See [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).

## Operator interface

Discover and operate the default Host-free surface:

```bash
ordivon-harness capabilities
ordivon-harness --harness-state-root /var/lib/ordivon/harness store-init
ordivon-harness --harness-state-root /var/lib/ordivon/harness run RUN_CONTRACT.json --message 'Start the bounded Run'
ordivon-harness --harness-state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --harness-state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
ordivon-harness --harness-state-root /var/lib/ordivon/harness resume HARNESS_RUN_ID --message 'Additional caller input'
ordivon-harness --harness-state-root /var/lib/ordivon/harness recover HARNESS_RUN_ID
ordivon-harness --harness-state-root /var/lib/ordivon/harness doctor
```

`run` consumes a caller-authored `HarnessRunContract`; the CLI never synthesizes Objective, Context, Tool Grant, caller identity, or budget authority. Its executable profile is currently the canonical no-Tool DeepSeek surface. Tool-bearing Contracts must use the Host-free Python API with an application-supplied `HarnessRuntimeClient`.

Retained Host-backed work remains explicit compatibility state:

```bash
ordivon-harness --state-root /var/lib/ordivon/host host status TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host host inspect TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host host handoff TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host host cancel TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host host recover TASK_ID
```

Store backup/restore and cutover commands remain separate administrative surfaces. Independent `status` and `inspect` require neither Runtime nor Provider access. Recovery never authorizes blind redispatch of an uncertain Provider or Tool effect.

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
