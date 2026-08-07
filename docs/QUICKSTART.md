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
# Quick start

## Set up

```bash
uv sync
uvx ruff==0.15.17 check src tests scripts
uv run python -m unittest discover -s tests -v
```

Build and verify the exact installable artifact:

```bash
python -m build
python scripts/check_wheel.py dist
```

The wheel contains one runtime dependency: the exact Ordivon Protocol pin. It does not install Host or expose a Host extra.

## Initialize independent state

```bash
ordivon-harness --state-root /var/lib/ordivon/harness store-init
ordivon-harness capabilities
```

## Run

Create a caller-authored `HarnessRunContract` JSON. The CLI does not invent Objective, Context, caller identity, Tool grant, budget or completion authority.

```bash
ordivon-harness --state-root /var/lib/ordivon/harness \
  run RUN_CONTRACT.json --message 'Start the bounded Run'

ordivon-harness --state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
```

For the built-in DeepSeek profile, the Contract must bind the canonical no-Tool catalog/grant and the configured DeepSeek Adapter/model. A Tool-bearing application supplies a `HarnessRuntimeClient` through the Python API instead of the primary CLI.

## Pause and resume

```bash
ordivon-harness --state-root /var/lib/ordivon/harness \
  resume HARNESS_RUN_ID --message 'Additional caller input'
```

## Recovery

```bash
ordivon-harness --state-root /var/lib/ordivon/harness recover HARNESS_RUN_ID
```

Recovery is evidence-driven. A dispatched Provider or Tool operation with an ambiguous physical outcome is not blindly repeated.

## Python API

Use `ordivon_harness.api` for normal applications and `ordivon_harness.core` for advanced persistence/continuity composition. `ordivon_harness.host_external_adapter` is an explicit, Host-free integration helper when a higher-level Host wants to call an independent Harness Run.
