---
schema_version: 1
id: harness.quickstart
title: Harness Quick Start
type: guide
profile: engineering
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - builder
  - operator
  - agent
updated: 2026-08-05
summary: Minimal path from a clean checkout to deterministic verification, operator inspection and live read-only acceptance.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.status
  - harness.compatibility
  - harness.operations
---
# Harness Quick Start

## Install the exact graph

```bash
git clone https://github.com/zycxfyh/ordivon-harness.git
cd ordivon-harness
uv python install 3.12
uv sync --locked
uv lock --check
```

The base package uses the exact Protocol revision. The exact Host revision is an optional `host` extra and a repository development dependency, so `uv sync --locked` still installs the complete legacy regression graph. `pyproject.toml`, `uv.lock` and `_host_compat` metadata must agree. A plain editable `pip install` is not the canonical repository setup because it does not validate `uv.lock`.

For a built wheel, the base installation exposes `ordivon_harness.core` and independent `store-*` commands without Host. Install the `host` extra only for `ordivon_harness.api`, Host-backed Runner commands and current production compatibility.

## Run the portable contract

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

This proves deterministic lifecycle, compatibility, repository contracts, wheel metadata, a Host-free persistent Run in an isolated base installation, and the optional Host integration. It does not prove a reachable Runtime or external Provider.

## Deterministic Agent loop

Run the network-free demonstration:

```bash
python scripts/demo_deterministic_run.py
```

It uses a scripted Provider and in-memory Tool bridge to demonstrate:

```text
Provider turn
→ Tool request
→ bounded Tool observation
→ second Provider turn
→ candidate completion
→ public Trace and counters
```

It proves Harness loop semantics, not Host persistence or Runtime execution.

## Inspect existing Host-backed work

These commands require only the Host state root:

```bash
ordivon-harness --state-root /var/lib/ordivon/host status TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host inspect TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host handoff TASK_ID
```

`inspect` combines Harness status with an operator handoff capsule. It does not contact a Provider or Runtime.

## Inspect and activate the independent writer

Cutover is explicit and fail-closed. First initialize and doctor the independent root, then inventory both histories:

```bash
ordivon-harness --harness-state-root /var/lib/ordivon/harness store-init
ordivon-harness --state-root /var/lib/ordivon/host \
  --harness-state-root /var/lib/ordivon/harness cutover-inventory
ordivon-harness --state-root /var/lib/ordivon/host cutover-status
```

Activate only when the inventory reports no blockers:

```bash
ordivon-harness --state-root /var/lib/ordivon/host \
  --harness-state-root /var/lib/ordivon/harness cutover-activate
```

After activation, legacy write commands are disabled. Historical `status`, `inspect`, `handoff`, and Doctor remain read-only. Rollback is permitted only before any post-activation independent work exists.

## Configure live execution

Harness reuses Host configuration for Runtime endpoint and token location. DeepSeek uses a private secret file; Codex and Hermes use explicit local adapter configuration. Follow [`OPERATIONS.md`](OPERATIONS.md) and [`../SECURITY.md`](../SECURITY.md).

## Read-only live acceptance

On an owner-trusted machine with the configured Runtime and DeepSeek secret:

```bash
scripts/local-acceptance run
```

The gate runs the complete portable suite and an existing bounded read-only Host→Harness→Runtime scenario when the required environment is present. It emits a receipt bound to the current Harness, Host, Protocol and Runtime identities. It does not mutate the source repository.

## Resume and recover

```bash
ordivon-harness --state-root /var/lib/ordivon/host resume TASK_ID \
  --message 'Additional operator context'
ordivon-harness --state-root /var/lib/ordivon/host recover TASK_ID
```

Resume continues from durable public state. Recover first reconciles the current Provider Call and Tool Step identities; it never treats lost delivery as permission to create a new effect.
