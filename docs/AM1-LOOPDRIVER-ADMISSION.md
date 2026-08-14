# AM1 — LoopDriver Admission-Time Plasticity

Status: identity result retained; AM1 executable factory prototype superseded by AM2 contraction; no live replacement.

## Hypothesis

`OrdivonAgentLoop` implementation identity is morphology rather than constitution. Harness should be able to name a different loop implementation for one immutable Attempt without changing Tool authority, cognition authority, effect fencing, receipts, recovery, or caller/domain completion ownership.

## Retained seam

AM1 reuses `HarnessExecutionProfile.metadata`, whose complete bytes already participate in the profile digest. A reserved strict value may be supplied:

```json
{
  "loopDriver": {
    "driverId": "loop-driver:...",
    "driverDigest": "sha256:..."
  }
}
```

`compile_harness_attempt()` validates this shape and copies it into the exact Attempt system manifest. The manifest is already digest-bound by `HarnessRunContract.system_manifest_ref`; no Run Contract schema, new database, registry, Tool grant, or authority model is added.

`HarnessLoopDriverIdentity.from_compiled_attempt()` proves only that one compiled Attempt declared the exact `(driverId, driverDigest)` pair and binds that identity to the Attempt's system-manifest digest. It cannot load, execute, discover, replace, or promote code.

## Superseded AM1 prototype

The first AM1 prototype also let `StandaloneHarnessRunner` accept an application-supplied Loop factory. AM2 deliberately deleted that execution seam after two falsifiers:

1. the declared `driverDigest` did not mechanically prove the bytes/transitive code of the Python callable being executed;
2. `isinstance(..., OrdivonAgentLoop)` did not prove a subclass preserved durable Provider/Tool/recovery kernels.

The history is retained because the contraction is part of the result: **Loop identity is admitted; arbitrary Loop substitutability is not.**

## What the retained AM1 surface does not do

- no global LoopDriver registry;
- no executable Loop factory;
- no package discovery;
- no Cordis dependency graph;
- no in-process install/uninstall;
- no mutation of an admitted Run's action authority;
- no automatic driver choice by Harness;
- no same-process hot swap;
- no persistence promotion of arbitrary generated code;
- no claim that an internal multi-agent driver is automatically a World Entity topology.

## Evidence

Current tests verify:

- `loopDriver` participates in profile/manifest identity;
- malformed reserved metadata fails closed;
- `CompiledHarnessAttempt` round-trip retains the exact driver declaration;
- an identity for another driver is rejected;
- an identity cannot attach to another Run manifest;
- the identity object exposes no executable factory/build surface;
- `StandaloneHarnessRunner` exposes no LoopDriver binding parameter.

AM7 later proved the existing Agent-owned strategy-selection plane can choose a different morphology profile for a successor Attempt. AM8 proved this is sufficient for the current replacement gate; same-process live replacement remains rejected absent a reproduced need.

## Decision

Retain `loopDriver` as an exact Attempt morphology fact and `HarnessLoopDriverIdentity` as advanced research identity validation. Keep the default execution path exactly `OrdivonAgentLoop` until non-bypassable Provider/Tool/effect/recovery kernels are extracted strongly enough to support a real alternative driver.
