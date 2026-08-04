---
schema_version: 1
id: harness.domain-tool-bridge.p0
title: Domain Tool Bridge P0
type: architecture
profile: engineering
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - builder
  - agent
updated: 2026-08-04
summary: Public dependency-inverted Harness loop boundary for domain-owned Tool catalogs, grants, execution, and execution identity without a domain dependency.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.architecture
  - harness.authority
---
# Domain Tool Bridge P0

## Problem

The first-party Ordivon Agent Loop already accepted an internal `ToolBridge`, but the only supported application path constructed a Runtime-owned workspace bridge. Domain projects such as Security need the same Provider-neutral loop while retaining ownership of domain admission, world truth, and effect semantics.

Importing a domain package into Harness or representing domain actions as fake Runtime tools would invert ownership and corrupt evidence.

## Public boundary

Version `0.6` exposes:

```text
DomainToolCatalog
DomainToolBridge
DomainToolLoopPlan
DomainToolLoopRunner
```

A domain owns:

- the immutable Tool definitions and semantic revision;
- the Bridge implementation identity;
- allowed Tool selection for one loop;
- domain admission, external effects, truth, and verification;
- durable Actor or Task state when the domain is the owning control plane.

Harness owns:

- the Provider-neutral Agent loop;
- model and adapter invocation;
- budgets, cancellation, stopping, and observable Tool-call history;
- deterministic catalog/grant identity supplied to the model;
- rejection of unknown or ungranted Tool names before domain execution.

## Identity

`DomainToolLoopRunner.execution_identity(plan)` binds:

- Harness package and Domain Loop revision;
- Provider adapter and requested model identity;
- domain identity and catalog revision;
- full catalog digest and granted-catalog digest;
- ordered allowed Tool names;
- domain Bridge implementation identity;
- complete Loop budget.

Secrets and credential values are excluded. A consuming Actor or experiment must bind this returned identity into its own durable Trial or Assignment identity.

## Non-goals

P0 does not:

- create a universal domain Tool registry;
- persist Host Tasks or Harness Assignments;
- replace Runtime workspace Tool durability;
- infer whether a domain effect succeeded;
- allow Harness to import Security, Game, World, or another domain;
- provide credential pooling or model routing by itself.

Use `HarnessRunner` for Host-owned durable Assignments and Runtime Tools. Use `DomainToolLoopRunner` when another domain already owns the durable Actor/Contest boundary and needs a bounded Harness cognition loop.

## Acceptance

The executable tests prove that:

- a non-Runtime domain Tool completes a model → Tool → observation → conclusion loop;
- only granted Tool definitions are exposed to the model;
- unknown grants fail before any Provider call;
- catalog revision and Tool shape change identity;
- bridge, Provider, grant, and budget identities are inspectable;
- the Harness repository imports no Security code;
- the prior full Harness suite remains green.

## Next integration

Ordivon Security should define its own CAGE team-plan catalog and Bridge, map Harness stop codes into Security Actor proposal failures, and bind the Harness execution identity into Contest Trial identity. Provider credential leasing and replacement remain separate Harness work and must not enter domain secrets or Trial evidence.
