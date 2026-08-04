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
updated: 2026-08-04
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
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip check
uv lock --check
```

The package uses exact Git revisions for Host and Protocol. `pyproject.toml`, `uv.lock` and `_host_compat` metadata must agree.

## Run the portable contract

```bash
python -m compileall -q src tests scripts evals
python -m ruff check src tests scripts
python -W error::ResourceWarning -m unittest discover -s tests -v
python scripts/check_dependencies.py
python scripts/check_docs.py
python scripts/check_evidence.py
scripts/local-acceptance check
python -m pip wheel --no-deps --wheel-dir /tmp/ordivon-harness-wheel .
```

This proves deterministic lifecycle, compatibility and repository contracts. It does not prove a reachable Runtime or external Provider.

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
