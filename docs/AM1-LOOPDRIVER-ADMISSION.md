# AM1 — LoopDriver Admission-Time Plasticity

Status: experimental; not stable API; no live replacement.

## Hypothesis

`OrdivonAgentLoop` implementation identity is morphology rather than constitution. Harness should be able to bind a different loop implementation to one immutable Attempt without changing Tool authority, cognition authority, effect fencing, receipts, recovery, or caller/domain completion ownership.

## Smallest retained seam

AM1 intentionally reuses `HarnessExecutionProfile.metadata`, whose complete bytes already participate in the profile digest. A reserved strict value may be supplied:

```json
{
  "loopDriver": {
    "driverId": "loop-driver:...",
    "driverDigest": "sha256:..."
  }
}
```

`compile_harness_attempt()` validates this shape and copies it into the exact Attempt system manifest. The manifest is already digest-bound by `HarnessRunContract.system_manifest_ref`; no Run Contract schema, new database, registry, Tool grant, or authority model is added.

`HarnessLoopDriverBinding.from_compiled_attempt()` can then bind one application-supplied factory only when `(driverId, driverDigest)` exactly matches that compiled manifest. `StandaloneHarnessRunner` accepts the binding only when its manifest digest is the exact Contract manifest digest. The factory receives only the same already-composed adapter, Tool bridge, budget, deadline and cognition handlers that the built-in loop would receive.

## What AM1 does not do

- no global LoopDriver registry;
- no package discovery;
- no Cordis dependency graph;
- no in-process install/uninstall;
- no mutation of an admitted Run's action authority;
- no automatic driver choice by Harness;
- no same-process hot swap;
- no persistence promotion of arbitrary generated code;
- no claim that an internal multi-agent driver is automatically a World Entity topology.

## Evidence

Targeted compiler/binding tests verify:

- `loopDriver` participates in profile/manifest identity;
- malformed reserved metadata fails closed;
- CompiledHarnessAttempt round-trip retains the exact driver declaration;
- a binding for another driver is rejected;
- a valid binding cannot attach to another Run manifest.

The first post-change complete Harness unittest run passed 399 tests with 3 skipped before the dedicated binding tests were added; targeted AM1 coverage then passed 12/12. A final complete run remains the closeout gate.

## AM1 decision gate

The seam is **provisionally retained as advanced experimental composition**, not promoted to `HarnessAgentRun` or package-root API. AM2 must provide a materially different driver/workload falsifier before this becomes a supported product surface.

The default path remains exactly `OrdivonAgentLoop`. Absence of `loopDriver` metadata preserves historical Attempt manifest shape and behavior.

## Next pressure

AM2 should compare at least two morphology changes under the same owner-native invariants. The highest-value candidates are:

1. sequential loop vs a mechanically distinct coordinator that changes scheduling/control flow without new authority;
2. internal multi-agent cognition vs true persistent World Entity topology;
3. model/loop change after a clean checkpoint vs replacement while an owner-native consequence is outstanding.

Any result that needs a global registry, live HMR, or new durable owner must demonstrate a failure that the current admission-time seam cannot express.
